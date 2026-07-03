"""Server-authoritative invoice operations.

The client submits line items + intent; everything financial (totals, VAT,
stock, ledger, numbering) is computed and validated here, inside
transaction.atomic(). Views never write these side effects directly.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from finance.audit import log_action, model_snapshot
from finance.money import percent_of
from inventory.services import record_movement
from parties.models import LedgerEntry
from parties.services import record_payment

from .models import Invoice, NumberSeries

DEFAULT_PREFIXES = {
    'sale': 'S-',
    'purchase': 'B-',
    'sale_return': 'SR-',
    'purchase_return': 'BR-',
    'proforma': 'PF-',
}

# Which direction each document type moves stock and the party ledger.
# ('stock movement type or None', 'ledger entry type or None')
DOC_EFFECTS = {
    'sale': ('out', LedgerEntry.DEBIT),            # they owe us
    'purchase': ('in', LedgerEntry.CREDIT),        # we owe them
    'sale_return': ('return_in', LedgerEntry.CREDIT),
    'purchase_return': ('return_out', LedgerEntry.DEBIT),
    'proforma': (None, None),                      # no financial effect
}


class InvoiceError(ValueError):
    """Invalid invoice operation, safe to show to staff."""


def allocate_number(doc_type) -> str:
    """Next number in the doc type's series. Must run inside a transaction."""
    series, _ = (NumberSeries.objects.select_for_update()
                 .get_or_create(doc_type=doc_type,
                                defaults={'prefix': DEFAULT_PREFIXES.get(doc_type, '')}))
    number = f'{series.prefix}{series.next_number:0{series.padding}d}'
    series.next_number += 1
    series.save(update_fields=['next_number'])
    return number


def recompute_totals(invoice):
    """Recompute and persist all money fields from the invoice's items.

    Integer-Rial math throughout. The header discount is allocated across
    lines proportionally to their net value (remainder goes to the last
    line), then VAT applies per line — a line's own vat_rate overrides the
    invoice rate.
    """
    items = list(invoice.items.all())
    if not items:
        raise InvoiceError('فاکتور باید حداقل یک قلم داشته باشد.')

    for item in items:
        if item.quantity <= 0:
            raise InvoiceError('تعداد هر قلم باید بزرگ‌تر از صفر باشد.')
        if item.discount > item.gross:
            raise InvoiceError(f'تخفیف قلم «{item.label}» از مبلغ آن بیشتر است.')

    subtotal = sum(item.gross for item in items)
    items_discount = sum(item.discount for item in items)
    base_total = subtotal - items_discount

    header_discount = invoice.discount
    if header_discount > base_total:
        raise InvoiceError('تخفیف کلی از جمع فاکتور بیشتر است.')

    # Allocate the header discount over lines by their net share.
    tax = 0
    allocated = 0
    for index, item in enumerate(items):
        if base_total > 0:
            if index == len(items) - 1:
                alloc = header_discount - allocated
            else:
                alloc = header_discount * item.net // base_total
                allocated += alloc
        else:
            alloc = 0
        taxable = item.net - alloc
        rate = item.vat_rate if item.vat_rate is not None else invoice.vat_rate
        tax += percent_of(taxable, rate)

    invoice.subtotal = subtotal
    invoice.items_discount = items_discount
    invoice.tax = tax
    invoice.total = base_total - header_discount + tax
    invoice.save(update_fields=['subtotal', 'items_discount', 'tax', 'total'])
    return invoice


@transaction.atomic
def issue_invoice(invoice, user):
    """Issue a draft: allocate its number, move stock, write the party
    ledger, and record any immediate payment — all or nothing."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != 'draft':
        raise InvoiceError('فقط پیش‌نویس‌ها قابل صدور هستند.')
    if invoice.party is None:
        raise InvoiceError('طرف حساب فاکتور مشخص نیست.')

    before = model_snapshot(invoice)
    recompute_totals(invoice)

    if invoice.paid_amount > invoice.total:
        raise InvoiceError('مبلغ پرداختی از جمع فاکتور بیشتر است.')

    stock_type, ledger_type = DOC_EFFECTS[invoice.doc_type]

    # Allocate the series number first so stock/ledger rows reference it;
    # a failure later in this transaction rolls the allocation back too.
    invoice.invoice_number = allocate_number(invoice.doc_type)

    # 1) stock movements (product lines only; service lines skip)
    if stock_type:
        for item in invoice.items.select_related('product'):
            if item.product_id is None:
                continue
            record_movement(
                item.product, stock_type, item.quantity,
                user=user,
                reference=invoice.invoice_number,
                unit_cost=item.unit_price if stock_type == 'in' else None,
                source=invoice,
            )

    # 2) party ledger for the full document amount
    if ledger_type and invoice.total > 0:
        LedgerEntry.objects.create(
            party=invoice.party,
            entry_type=ledger_type,
            amount=invoice.total,
            description=f'{invoice.get_doc_type_display()} {invoice.invoice_number}',
            content_type=ContentType.objects.get_for_model(Invoice),
            object_id=invoice.pk,
            created_by=user,
        )

    # 3) immediate settlement (full or partial payment on issue)
    if ledger_type and invoice.paid_amount > 0:
        record_payment(
            party=invoice.party,
            kind='receipt' if ledger_type == LedgerEntry.DEBIT else 'payment',
            method='card' if invoice.settlement_type == 'card' else 'cash',
            amount=invoice.paid_amount,
            description=f'تسویه هنگام صدور {invoice.invoice_number}',
            user=user,
        )

    # 4) snapshot + status
    invoice.customer_name = invoice.party.name
    invoice.customer_mobile = invoice.party.mobile
    invoice.customer_address = invoice.party.address
    invoice.status = 'issued'
    invoice.issued_at = timezone.now()
    invoice.issued_by = user
    invoice.is_paid = invoice.paid_amount >= invoice.total
    invoice.save()

    log_action(user, 'status', invoice, before=before, after=model_snapshot(invoice))
    return invoice


@transaction.atomic
def cancel_invoice(invoice, user):
    """Cancel an issued document with reversing stock and ledger entries.

    Payments recorded at issue are NOT auto-reversed — the accountant
    settles those explicitly from the party's ledger.
    """
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != 'issued':
        raise InvoiceError('فقط اسناد صادرشده قابل ابطال هستند.')

    before = model_snapshot(invoice)
    stock_type, ledger_type = DOC_EFFECTS[invoice.doc_type]

    REVERSE_STOCK = {'out': 'return_in', 'in': 'return_out',
                     'return_in': 'out', 'return_out': 'in'}
    if stock_type:
        for item in invoice.items.select_related('product'):
            if item.product_id is None:
                continue
            record_movement(
                item.product, REVERSE_STOCK[stock_type], item.quantity,
                user=user,
                reference=f'ابطال {invoice.invoice_number}',
                source=invoice,
                allow_negative=True,
            )

    if ledger_type and invoice.total > 0:
        LedgerEntry.objects.create(
            party=invoice.party,
            entry_type=LedgerEntry.CREDIT if ledger_type == LedgerEntry.DEBIT else LedgerEntry.DEBIT,
            amount=invoice.total,
            description=f'ابطال {invoice.get_doc_type_display()} {invoice.invoice_number}',
            content_type=ContentType.objects.get_for_model(Invoice),
            object_id=invoice.pk,
            created_by=user,
        )

    invoice.status = 'cancelled'
    invoice.cancelled_at = timezone.now()
    invoice.cancelled_by = user
    invoice.save(update_fields=['status', 'cancelled_at', 'cancelled_by'])

    log_action(user, 'status', invoice, before=before, after=model_snapshot(invoice))
    return invoice
