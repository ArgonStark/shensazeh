"""Outbound SMS with logging: transactional (invoice) and campaign sends.

Everything goes through the SMSProvider abstraction (accounts.sms_service);
the provider is chosen by the SMS_PROVIDER env setting. Sending is
best-effort — failures are logged, never raised into a financial flow.
"""

import logging

from django.conf import settings
from django.utils import timezone

from accounts.sms_service import get_sms_provider
from finance.money import rial_to_toman

from .models import Campaign, SMSLog

logger = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def render_template(template: str, variables: dict) -> str:
    """'{name} عزیز' + {'name': 'علی'} → 'علی عزیز'; unknown keys stay literal."""
    return template.format_map(_SafeDict(variables))


def send_sms(mobile, message, *, party=None, campaign=None, user=None) -> bool:
    mobile = (mobile or '').strip()
    if not mobile:
        return False
    ok = get_sms_provider().send(mobile, message)
    SMSLog.objects.create(
        mobile=mobile, message=message,
        status='sent' if ok else 'failed',
        provider=getattr(settings, 'SMS_PROVIDER', 'console'),
        party=party, campaign=campaign, created_by=user,
    )
    return ok


def send_invoice_sms(invoice, user=None) -> bool:
    """Post-issue SMS to the invoice's party — opt-in via SiteSetting."""
    from admin_panel.models import SiteSetting
    site = SiteSetting.load()
    if not site.invoice_sms_enabled or invoice.doc_type != 'sale':
        return False
    if not invoice.party or not invoice.party.mobile:
        return False
    message = render_template(site.invoice_sms_template, {
        'name': invoice.party.name,
        'number': invoice.invoice_number,
        'amount': f'{rial_to_toman(invoice.total):,}',
        'due_date': invoice.due_date.strftime('%Y/%m/%d') if invoice.due_date else '',
        'shop': site.site_name,
    })
    return send_sms(invoice.party.mobile, message, party=invoice.party, user=user)


def campaign_recipients(campaign):
    from parties.models import Party
    qs = Party.objects.filter(is_active=True).exclude(mobile='')
    if campaign.party_type:
        qs = qs.filter(party_type__in=[campaign.party_type, 'both'])
    if campaign.tag_id:
        qs = qs.filter(tags=campaign.tag)
    return qs.distinct()


def send_campaign(campaign, user=None):
    """Send a campaign synchronously (suited to a small shop's list sizes);
    each send is logged individually. A campaign can only be sent once."""
    if campaign.is_sent:
        raise ValueError('این کمپین قبلاً ارسال شده است.')
    sent = 0
    for party in campaign_recipients(campaign):
        message = render_template(campaign.message, {
            'name': party.name, 'mobile': party.mobile, 'city': party.city,
        })
        if send_sms(party.mobile, message, party=party, campaign=campaign, user=user):
            sent += 1
    campaign.sent_at = timezone.now()
    campaign.sent_count = sent
    campaign.save(update_fields=['sent_at', 'sent_count'])
    return sent
