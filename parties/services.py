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


def ledger_rows_with_balance(party):
    """Party's ledger oldest-first, each row annotated with the running balance."""
    rows = []
    balance = 0
    for entry in party.ledger_entries.order_by('created_at', 'id'):
        balance += entry.signed_amount
        rows.append({'entry': entry, 'balance': balance})
    return rows
