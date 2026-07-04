"""Installment schedules and payments — server-authoritative, integer Rial.

Interest formulas (P = principal in Rial, r = annual rate %, n = number of
monthly installments):

1. none:      I = 0. Each installment = P // n, remainder on the last one.
2. simple:    I = P × r/100 × n/12 (floor). Total = P + I split equally,
              remainder on the last installment.
3. reducing:  standard amortized loan on the declining balance with monthly
              rate i = r/1200: A = P·i·(1+i)ⁿ / ((1+i)ⁿ − 1). A is rounded to
              whole Rial; the last installment absorbs the rounding so the
              schedule sums exactly to n·A' (total interest = sum − P).
"""

import jdatetime
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from finance.audit import log_action
from parties.models import LedgerEntry
from parties.services import record_payment

from .models import Installment, InstallmentPlan


class InstallmentError(ValueError):
    """Invalid installment operation, safe to show to staff."""


def add_jalali_months(date, months):
    """Step a jdatetime.date forward by whole Jalali months, clamping the day
    to the target month's length (1404/06/31 + 1 → 1404/07/30)."""
    total = (date.year * 12) + (date.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    days_in_month = jdatetime.j_days_in_month[month - 1]
    if month == 12 and jdatetime.date(year, 1, 1).isleap():
        days_in_month = 30
    return jdatetime.date(year, month, min(date.day, days_in_month))


def build_schedule(principal, method, annual_rate, count):
    """(total_interest, [amount_1..amount_n]) — amounts sum to principal+interest."""
    principal = int(principal)
    count = int(count)
    if principal <= 0:
        raise InstallmentError('اصل مبلغ باید بزرگ‌تر از صفر باشد.')
    if not 1 <= count <= 60:
        raise InstallmentError('تعداد اقساط باید بین ۱ و ۶۰ باشد.')
    if method not in dict(InstallmentPlan.METHOD_CHOICES):
        raise InstallmentError('روش سود نامعتبر است.')
    if method != 'none' and annual_rate <= 0:
        raise InstallmentError('نرخ سود باید بزرگ‌تر از صفر باشد.')

    if method == 'none':
        interest = 0
        total = principal
        base = total // count
        amounts = [base] * count
        amounts[-1] += total - base * count
    elif method == 'simple':
        interest = (principal * annual_rate * count) // (100 * 12)
        total = principal + interest
        base = total // count
        amounts = [base] * count
        amounts[-1] += total - base * count
    else:  # reducing
        i = annual_rate / 1200
        factor = (1 + i) ** count
        payment = round(principal * i * factor / (factor - 1))
        # Replay the amortization so the last payment closes the balance exactly.
        balance = principal
        amounts = []
        for _ in range(count - 1):
            month_interest = round(balance * i)
            balance -= (payment - month_interest)
            amounts.append(payment)
        last_interest = round(balance * i)
        amounts.append(balance + last_interest)
        total = sum(amounts)
        interest = total - principal

    return interest, amounts


@transaction.atomic
def create_installment_plan(invoice, *, method, annual_rate, count, start_date, user):
    """Create the plan + rows and post the interest to the party ledger.

    The invoice's outstanding remainder becomes the principal; interest is an
    additional debit so the ledger matches what the customer must pay."""
    if invoice.status != 'issued' or invoice.doc_type != 'sale':
        raise InstallmentError('طرح اقساط فقط برای فاکتور فروش صادرشده ممکن است.')
    if hasattr(invoice, 'installment_plan'):
        raise InstallmentError('برای این فاکتور قبلاً طرح اقساط ثبت شده است.')
    principal = invoice.remaining_amount
    if principal <= 0:
        raise InstallmentError('این فاکتور مانده‌ای برای قسط‌بندی ندارد.')
    if start_date is None or start_date < jdatetime.date.today():
        raise InstallmentError('سررسید قسط اول باید امروز یا بعد از آن باشد.')

    interest, amounts = build_schedule(principal, method, annual_rate, count)

    plan = InstallmentPlan.objects.create(
        invoice=invoice, party=invoice.party, principal=principal,
        method=method, annual_rate=annual_rate if method != 'none' else 0,
        count=count, total_interest=interest, total_payable=principal + interest,
        start_date=start_date, created_by=user,
    )
    Installment.objects.bulk_create([
        Installment(plan=plan, seq=seq, amount=amount,
                    due_date=add_jalali_months(start_date, seq - 1))
        for seq, amount in enumerate(amounts, start=1)
    ])

    if interest > 0:
        LedgerEntry.objects.create(
            party=invoice.party, entry_type=LedgerEntry.DEBIT, amount=interest,
            description=f'سود اقساط {invoice.invoice_number}',
            content_type=ContentType.objects.get_for_model(InstallmentPlan),
            object_id=plan.pk, created_by=user,
        )

    invoice.settlement_type = 'installment'
    invoice.due_date = start_date
    invoice.save(update_fields=['settlement_type', 'due_date'])

    log_action(user, 'create', plan)
    return plan


@transaction.atomic
def pay_installment(installment, amount, user, method='cash'):
    """Receive money against one installment (partial allowed, no overpay).

    Posts a receipt to the party ledger; when the whole plan settles, the
    invoice is flagged paid. (invoice.paid_amount stays as the issue-time
    payment — the plan tracks the rest.)"""
    installment = Installment.objects.select_for_update().select_related('plan__invoice', 'plan__party').get(pk=installment.pk)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise InstallmentError('مبلغ نامعتبر است.')
    if amount <= 0:
        raise InstallmentError('مبلغ باید بزرگ‌تر از صفر باشد.')
    if amount > installment.remaining:
        raise InstallmentError(f'مبلغ از مانده این قسط ({installment.remaining:,} ریال) بیشتر است.')

    record_payment(
        party=installment.plan.party, kind='receipt', method=method, amount=amount,
        description=f'قسط {installment.seq} از {installment.plan.invoice.invoice_number}',
        user=user,
    )
    installment.paid_amount += amount
    if installment.is_paid:
        installment.paid_at = timezone.now()
    installment.save(update_fields=['paid_amount', 'paid_at'])

    plan = installment.plan
    if plan.is_settled and not plan.invoice.is_paid:
        plan.invoice.is_paid = True
        plan.invoice.save(update_fields=['is_paid'])
    return installment
