"""Cheque lifecycle with its ledger side effects."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from finance.audit import log_action, model_snapshot
from parties.models import LedgerEntry

from .models import Cheque


class ChequeError(ValueError):
    """Invalid cheque operation, safe to show to staff."""


VALID_TRANSITIONS = {
    'pending': {'cleared', 'bounced'},
    'cleared': set(),   # final
    'bounced': set(),   # final
}


@transaction.atomic
def set_cheque_status(cheque, new_status, user):
    """pending → cleared posts the party ledger; bounced posts nothing
    (a bounced cheque never was money — the original debt stays open)."""
    cheque = Cheque.objects.select_for_update().get(pk=cheque.pk)
    if new_status not in dict(Cheque.STATUS_CHOICES):
        raise ChequeError('وضعیت نامعتبر است.')
    if new_status not in VALID_TRANSITIONS[cheque.status]:
        raise ChequeError(
            f'تغییر وضعیت از «{cheque.get_status_display()}» ممکن نیست.')

    before = model_snapshot(cheque)

    if new_status == 'cleared':
        LedgerEntry.objects.create(
            party=cheque.party,
            # received cheque cleared → their debt shrinks (credit);
            # our issued cheque cleared → our debt to them shrinks (debit)
            entry_type=LedgerEntry.CREDIT if cheque.direction == 'received' else LedgerEntry.DEBIT,
            amount=cheque.amount,
            description=f'وصول چک {cheque.serial} ({cheque.bank_name})',
            content_type=ContentType.objects.get_for_model(Cheque),
            object_id=cheque.pk,
            created_by=user,
        )

    cheque.status = new_status
    cheque.status_changed_at = timezone.now()
    cheque.save(update_fields=['status', 'status_changed_at'])
    log_action(user, 'status', cheque, before=before, after=model_snapshot(cheque))
    return cheque
