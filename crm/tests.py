from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.sms_service import ConsoleSMSProvider, KavenegarSMSProvider, get_sms_provider
from admin_panel.models import SiteSetting
from admin_panel.permissions import apply_role_defaults
from parties.models import Party, PartyTag

from .models import Campaign, SMSLog
from .services import render_template, send_campaign, send_invoice_sms, send_sms


class ProviderSelectionTests(TestCase):
    def test_default_is_console(self):
        self.assertIsInstance(get_sms_provider(), ConsoleSMSProvider)

    @override_settings(SMS_PROVIDER='kavenegar')
    def test_kavenegar_selected(self):
        self.assertIsInstance(get_sms_provider(), KavenegarSMSProvider)

    @override_settings(SMS_PROVIDER='kavenegar', SMS_API_KEY='')
    def test_kavenegar_without_key_fails_safe(self):
        self.assertFalse(get_sms_provider().send('09120000000', 'x'))

    @override_settings(SMS_PROVIDER='unknown')
    def test_unknown_falls_back_to_console(self):
        self.assertIsInstance(get_sms_provider(), ConsoleSMSProvider)


class TemplateRenderTests(TestCase):
    def test_variables_replaced(self):
        result = render_template('{name} عزیز، فاکتور {number}', {'name': 'علی', 'number': 'S-1'})
        self.assertEqual(result, 'علی عزیز، فاکتور S-1')

    def test_unknown_variable_stays_literal(self):
        self.assertEqual(render_template('سلام {ghost}', {'name': 'x'}), 'سلام {ghost}')


class SendSMSTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='گیرنده', mobile='09121234567')

    def test_send_logs_success(self):
        ok = send_sms('09121234567', 'تست', party=self.party)
        self.assertTrue(ok)
        log = SMSLog.objects.get()
        self.assertEqual(log.status, 'sent')
        self.assertEqual(log.party, self.party)
        self.assertEqual(log.provider, 'console')

    def test_empty_mobile_not_sent(self):
        self.assertFalse(send_sms('', 'x'))
        self.assertEqual(SMSLog.objects.count(), 0)


class InvoiceSMSTests(TestCase):
    def setUp(self):
        from orders.models import Invoice, InvoiceItem
        from orders.services import issue_invoice
        from store.models import Category, Product
        self.user = User.objects.create_user(username='sms', mobile='09120009000', password='x', is_staff=True)
        self.party = Party.objects.create(name='مشتری پیامکی', mobile='09121112222')
        category = Category.objects.create(name='ابزار', slug='t2')
        product = Product.objects.create(name='انبردست', slug='plier', category=category,
                                         price=500_000, stock=10)
        invoice = Invoice.objects.create(doc_type='sale', party=self.party,
                                         customer_name=self.party.name, settlement_type='credit')
        InvoiceItem.objects.create(invoice=invoice, product=product, quantity=2, unit_price=500_000)
        self.invoice = issue_invoice(invoice, self.user)

    def test_disabled_by_default(self):
        self.assertFalse(send_invoice_sms(self.invoice, self.user))
        self.assertEqual(SMSLog.objects.count(), 0)

    def test_sends_when_enabled_with_variables(self):
        site = SiteSetting.load()
        site.invoice_sms_enabled = True
        site.save()
        self.assertTrue(send_invoice_sms(self.invoice, self.user))
        log = SMSLog.objects.get()
        self.assertIn(self.invoice.invoice_number, log.message)
        self.assertIn('100,000', log.message)  # 1,000,000 Rial → 100,000 Toman
        self.assertIn(self.party.name, log.message)

    def test_no_mobile_no_sms(self):
        site = SiteSetting.load()
        site.invoice_sms_enabled = True
        site.save()
        self.party.mobile = ''
        self.party.save()
        self.invoice.refresh_from_db()
        self.assertFalse(send_invoice_sms(self.invoice, self.user))


class CampaignTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='camp', mobile='09120009001', password='x', is_staff=True)
        apply_role_defaults(self.user, 'manager')
        self.tag = PartyTag.objects.create(name='عمده')
        self.wholesale = Party.objects.create(name='عمده‌فروش', mobile='09123330000', party_type='customer')
        self.wholesale.tags.add(self.tag)
        self.retail = Party.objects.create(name='خرده', mobile='09123330001', party_type='customer')
        self.supplier = Party.objects.create(name='تأمین', mobile='09123330002', party_type='supplier')
        Party.objects.create(name='بی‌موبایل', mobile='', party_type='customer')

    def test_tag_segmentation(self):
        campaign = Campaign.objects.create(name='ویژه عمده', message='{name} عزیز', tag=self.tag)
        sent = send_campaign(campaign, self.user)
        self.assertEqual(sent, 1)
        log = SMSLog.objects.get()
        self.assertEqual(log.party, self.wholesale)
        self.assertEqual(log.message, 'عمده‌فروش عزیز')
        campaign.refresh_from_db()
        self.assertTrue(campaign.is_sent)
        self.assertEqual(campaign.sent_count, 1)

    def test_type_segmentation_skips_no_mobile(self):
        campaign = Campaign.objects.create(name='مشتریان', message='x', party_type='customer')
        sent = send_campaign(campaign, self.user)
        self.assertEqual(sent, 2)  # wholesale + retail; supplier & no-mobile excluded

    def test_campaign_sends_only_once(self):
        campaign = Campaign.objects.create(name='یکبار', message='x')
        send_campaign(campaign, self.user)
        with self.assertRaises(ValueError):
            send_campaign(campaign, self.user)

    def test_panel_flow(self):
        self.client.force_login(self.user)
        self.client.post(reverse('admin_panel:campaign_create'),
                         {'name': 'پنل', 'message': 'سلام {name}', 'party_type': '', 'tag': ''})
        campaign = Campaign.objects.get(name='پنل')
        response = self.client.get(reverse('admin_panel:campaign_list'))
        self.assertContains(response, 'پنل')
        self.client.post(reverse('admin_panel:campaign_send', args=[campaign.pk]))
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_count, 3)
        self.assertEqual(self.client.get(reverse('admin_panel:sms_log_list')).status_code, 200)

    def test_warehouse_cannot_see_sms(self):
        wh = User.objects.create_user(username='whs', mobile='09120009002', password='x', is_staff=True)
        apply_role_defaults(wh, 'warehouse')
        self.client.force_login(wh)
        self.assertEqual(self.client.get(reverse('admin_panel:sms_log_list')).status_code, 403)
