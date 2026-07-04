"""Server-authoritative operations on party ledgers.

All multi-step financial writes go through these functions inside
transaction.atomic() — views must never write LedgerEntry/Payment directly.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from finance.audit import log_action

from .models import LedgerEntry, Payment


class LedgerError(ValueError):
    """Invalid ledger operation (bad amount, inactive party, …)."""


@transaction.atomic
def record_payment(*, party, kind, method, amount, reference='', description='', user=None):
    """Record a manual receipt/payment and its ledger entry atomically.

    receipt  → credit entry (the party's debt to us shrinks)
    payment  → debit  entry (our debt to the party shrinks)
    """
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise LedgerError('مبلغ نامعتبر است.')
    if amount <= 0:
        raise LedgerError('مبلغ باید بزرگ‌تر از صفر باشد.')
    if kind not in dict(Payment.KIND_CHOICES):
        raise LedgerError('نوع تراکنش نامعتبر است.')
    if method not in dict(Payment.METHOD_CHOICES):
        raise LedgerError('روش پرداخت نامعتبر است.')

    payment = Payment.objects.create(
        party=party, kind=kind, method=method, amount=amount,
        reference=reference, description=description, created_by=user,
    )
    default_desc = ('دریافت از' if kind == 'receipt' else 'پرداخت به') + f' {party.name}'
    entry = LedgerEntry.objects.create(
        party=party,
        entry_type=LedgerEntry.CREDIT if kind == 'receipt' else LedgerEntry.DEBIT,
        amount=amount,
        description=description or default_desc,
        content_type=ContentType.objects.get_for_model(Payment),
        object_id=payment.pk,
        created_by=user,
    )
    payment.ledger_entry = entry
    payment.save(update_fields=['ledger_entry'])
    log_action(user, 'create', payment)
    return payment


@transaction.atomic
def apply_payment(party, amount, *, user=None, method='cash', reference='', description=''):
    """Receive money and auto-settle the party's open debts.

    Allocation priority (deliberate and fixed — tested in parties.tests):
      1. overdue installments, oldest due date first
      2. issued unpaid sale invoices WITHOUT an installment plan, oldest first
      3. remaining (future) open installments, oldest due date first
      4. whatever is left simply stays as the ledger credit from step 0

    The party ledger gets exactly ONE credit (the received amount) via
    record_payment; allocation only updates document paid/settled flags, so
    the ledger stays balanced and every step is inside this transaction.

    Returns (payment, allocations) where allocations is a list of
    ('installment'|'invoice', obj, allocated_amount).
    """
    import jdatetime
    from django.db.models import F
    from django.utils import timezone

    from installments.models import Installment

    payment = record_payment(party=party, kind='receipt', method=method, amount=amount,
                             reference=reference,
                             description=description or f'دریافت با تسویه خودکار — {party.name}',
                             user=user)
    remaining = payment.amount
    allocations = []
    today = jdatetime.date.today()

    def open_installments():
        return (Installment.objects.select_for_update()
                .filter(plan__party=party, paid_amount__lt=F('amount'))
                .select_related('plan__invoice'))

    def settle_installment(installment):
        nonlocal remaining
        alloc = min(remaining, installment.remaining)
        if alloc <= 0:
            return
        installment.paid_amount += alloc
        if installment.is_paid:
            installment.paid_at = timezone.now()
        installment.save(update_fields=['paid_amount', 'paid_at'])
        remaining -= alloc
        allocations.append(('installment', installment, alloc))
        plan = installment.plan
        if plan.is_settled and not plan.invoice.is_paid:
            plan.invoice.is_paid = True
            plan.invoice.save(update_fields=['is_paid'])

    # 1) overdue installments
    for installment in open_installments().filter(due_date__lt=today).order_by('due_date', 'seq'):
        if remaining <= 0:
            break
        settle_installment(installment)

    # 2) unpaid issued sale invoices without a plan, oldest first
    if remaining > 0:
        invoices = (party.invoices.select_for_update()
                    .filter(doc_type='sale', status='issued', is_paid=False,
                            installment_plan__isnull=True)
                    .order_by('created_at', 'id'))
        for invoice in invoices:
            if remaining <= 0:
                break
            alloc = min(remaining, invoice.remaining_amount)
            if alloc <= 0:
                continue
            invoice.paid_amount += alloc
            invoice.is_paid = invoice.paid_amount >= invoice.total
            invoice.save(update_fields=['paid_amount', 'is_paid'])
            remaining -= alloc
            allocations.append(('invoice', invoice, alloc))

    # 3) future open installments
    if remaining > 0:
        for installment in open_installments().filter(due_date__gte=today).order_by('due_date', 'seq'):
            if remaining <= 0:
                break
            settle_installment(installment)

    # 4) `remaining` needs no action — the credit already sits on the ledger.
    return payment, allocations


def ledger_rows_with_balance(party):
    """Party's ledger oldest-first, each row annotated with the running balance."""
    rows = []
    balance = 0
    for entry in party.ledger_entries.order_by('created_at', 'id'):
        balance += entry.signed_amount
        rows.append({'entry': entry, 'balance': balance})
    return rows
