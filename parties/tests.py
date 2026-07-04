from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.permissions import apply_role_defaults
from finance.models import AuditLog

from .models import LedgerEntry, Party, Payment
from .services import LedgerError, ledger_rows_with_balance, record_payment


class LedgerModelTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='حاج قاسم بنایی', party_type='customer')

    def test_entries_are_immutable(self):
        entry = LedgerEntry.objects.create(
            party=self.party, entry_type=LedgerEntry.DEBIT, amount=1000, description='فروش نسیه')
        entry.amount = 2000
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()

    def test_balance_sign_convention(self):
        LedgerEntry.objects.create(party=self.party, entry_type=LedgerEntry.DEBIT, amount=5_000_000, description='فاکتور فروش')
        LedgerEntry.objects.create(party=self.party, entry_type=LedgerEntry.CREDIT, amount=2_000_000, description='دریافت نقدی')
        self.assertEqual(self.party.balance, 3_000_000)  # party owes us

    def test_running_balance_rows(self):
        LedgerEntry.objects.create(party=self.party, entry_type=LedgerEntry.DEBIT, amount=100, description='الف')
        LedgerEntry.objects.create(party=self.party, entry_type=LedgerEntry.CREDIT, amount=300, description='ب')
        rows = ledger_rows_with_balance(self.party)
        self.assertEqual([r['balance'] for r in rows], [100, -200])


class RecordPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='acc', mobile='09120001000', password='x', is_staff=True)
        self.party = Party.objects.create(name='تأمین‌کننده سیمان', party_type='supplier')

    def test_receipt_creates_credit_entry(self):
        payment = record_payment(party=self.party, kind='receipt', method='cash',
                                 amount=1_500_000, user=self.user)
        entry = payment.ledger_entry
        self.assertEqual(entry.entry_type, LedgerEntry.CREDIT)
        self.assertEqual(entry.amount, 1_500_000)
        self.assertEqual(entry.source, payment)
        self.assertEqual(self.party.balance, -1_500_000)
        self.assertTrue(AuditLog.objects.filter(action='create', object_id=payment.pk).exists())

    def test_payment_creates_debit_entry(self):
        payment = record_payment(party=self.party, kind='payment', method='transfer',
                                 amount=700_000, user=self.user)
        self.assertEqual(payment.ledger_entry.entry_type, LedgerEntry.DEBIT)
        self.assertEqual(self.party.balance, 700_000)

    def test_zero_or_negative_amount_rejected(self):
        for bad in (0, -100, 'abc', None):
            with self.assertRaises(LedgerError):
                record_payment(party=self.party, kind='receipt', method='cash', amount=bad)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_invalid_kind_rejected(self):
        with self.assertRaises(LedgerError):
            record_payment(party=self.party, kind='steal', method='cash', amount=10)


class AutoSettlementTests(TestCase):
    """apply_payment priority: overdue installments → open invoices → future
    installments → remainder stays as credit."""

    def setUp(self):
        import jdatetime

        from orders.models import Invoice, InvoiceItem
        from orders.services import issue_invoice
        from store.models import Category, Product
        self.user = User.objects.create_user(username='as', mobile='09120007000', password='x', is_staff=True)
        self.party = Party.objects.create(name='بدهکار بزرگ')
        category = Category.objects.create(name='مصالح', slug='m1')
        self.product = Product.objects.create(name='بلوک', slug='block', category=category,
                                              price=1_000_000, stock=1000)
        self.jdate = jdatetime

        def make_issued_invoice(qty):
            invoice = Invoice.objects.create(doc_type='sale', party=self.party,
                                             customer_name=self.party.name, settlement_type='credit')
            InvoiceItem.objects.create(invoice=invoice, product=self.product,
                                       quantity=qty, unit_price=1_000_000)
            return issue_invoice(invoice, self.user)

        self.make_issued_invoice = make_issued_invoice

    def _make_plan(self, invoice, count, start):
        from installments.services import create_installment_plan
        return create_installment_plan(invoice, method='none', annual_rate=0,
                                       count=count, start_date=start, user=self.user)

    def test_priority_and_partial_allocation(self):
        from parties.services import apply_payment
        today = self.jdate.date.today()

        # Plan with a 2,000,000 installment made overdue by hand
        plan_invoice = self.make_issued_invoice(4)   # 4,000,000
        plan = self._make_plan(plan_invoice, 2, today + self.jdate.timedelta(days=3))
        first = plan.installments.first()
        type(first).objects.filter(pk=first.pk).update(due_date=today - self.jdate.timedelta(days=10))

        # Plain open invoice 3,000,000
        open_invoice = self.make_issued_invoice(3)

        # Pay 4,500,000: 2,000,000 → overdue installment, 2,500,000 → invoice (partial)
        _, allocations = apply_payment(self.party, 4_500_000, user=self.user)
        self.assertEqual([(kind, alloc) for kind, _, alloc in allocations],
                         [('installment', 2_000_000), ('invoice', 2_500_000)])
        first.refresh_from_db()
        self.assertTrue(first.is_paid)
        open_invoice.refresh_from_db()
        self.assertFalse(open_invoice.is_paid)
        self.assertEqual(open_invoice.remaining_amount, 500_000)

    def test_remainder_becomes_credit(self):
        from parties.services import apply_payment
        invoice = self.make_issued_invoice(1)  # 1,000,000 debt
        _, allocations = apply_payment(self.party, 1_500_000, user=self.user)
        self.assertEqual(sum(a for _, _, a in allocations), 1_000_000)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_paid)
        # ledger: debit 1M, credit 1.5M → party is 500k in credit
        self.assertEqual(self.party.balance, -500_000)

    def test_future_installments_after_invoices(self):
        from parties.services import apply_payment
        today = self.jdate.date.today()
        plan_invoice = self.make_issued_invoice(2)   # plan: 2 × 1,000,000, future
        plan = self._make_plan(plan_invoice, 2, today + self.jdate.timedelta(days=5))
        open_invoice = self.make_issued_invoice(1)   # 1,000,000

        _, allocations = apply_payment(self.party, 2_000_000, user=self.user)
        kinds = [kind for kind, _, _ in allocations]
        self.assertEqual(kinds, ['invoice', 'installment'])  # invoice before future installments
        open_invoice.refresh_from_db()
        self.assertTrue(open_invoice.is_paid)
        self.assertEqual(plan.installments.first().plan.paid_total, 1_000_000)

    def test_single_ledger_credit_for_whole_amount(self):
        from parties.services import apply_payment
        self.make_issued_invoice(2)
        apply_payment(self.party, 5_000_000, user=self.user)
        credits = LedgerEntry.objects.filter(party=self.party, entry_type=LedgerEntry.CREDIT)
        self.assertEqual(credits.count(), 1)
        self.assertEqual(credits.get().amount, 5_000_000)

    def test_plan_fully_settled_marks_invoice_paid(self):
        from parties.services import apply_payment
        today = self.jdate.date.today()
        plan_invoice = self.make_issued_invoice(2)
        self._make_plan(plan_invoice, 2, today + self.jdate.timedelta(days=5))
        apply_payment(self.party, 2_000_000, user=self.user)
        plan_invoice.refresh_from_db()
        self.assertTrue(plan_invoice.is_paid)


class PartyPanelViewTests(TestCase):
    def setUp(self):
        self.accountant = User.objects.create_user(username='acc2', mobile='09120001001', password='x', is_staff=True)
        apply_role_defaults(self.accountant, 'accountant')
        self.warehouse = User.objects.create_user(username='wh', mobile='09120001002', password='x', is_staff=True)
        apply_role_defaults(self.warehouse, 'warehouse')
        self.party = Party.objects.create(name='مشتری تست', mobile='09121112233')

    def test_party_list_requires_permission(self):
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse('admin_panel:party_list')).status_code, 403)
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('admin_panel:party_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'مشتری تست')

    def test_party_create(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('admin_panel:party_create'), {
            'party_type': 'supplier', 'name': 'فروشنده آجر', 'company': '', 'mobile': '09125556677',
            'phone': '', 'national_id': '', 'economic_code': '', 'province': '', 'city': 'شیراز',
            'address': '', 'postal_code': '', 'notes': '', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Party.objects.filter(name='فروشنده آجر', party_type='supplier').exists())

    def test_payment_endpoint_writes_ledger(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('admin_panel:party_payment', args=[self.party.pk]), {
            'kind': 'receipt', 'method': 'card', 'amount': 250000, 'reference': '', 'description': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.party.balance, -250000)

    def test_ledger_page_shows_running_balance(self):
        record_payment(party=self.party, kind='payment', method='cash', amount=1_000_000, user=self.accountant)
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('admin_panel:party_ledger', args=[self.party.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '100,000')  # 1,000,000 Rial → 100,000 Toman

    def test_balance_report(self):
        record_payment(party=self.party, kind='payment', method='cash', amount=500_000, user=self.accountant)
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('admin_panel:party_balance_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'مشتری تست')

    def test_export_excel(self):
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('admin_panel:party_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

    def test_import_excel_roundtrip(self):
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['نام', 'نوع', 'شرکت', 'موبایل', 'تلفن', 'کد ملی', 'کد اقتصادی', 'استان', 'شهر', 'آدرس'])
        ws.append(['کارگاه بتن', 'تأمین‌کننده', '', '09127778899', '', '', '', 'فارس', 'شیراز', ''])
        ws.append(['مشتری تست', 'مشتری', '', '09121112233', '', '', '', '', '', ''])  # duplicate → skipped
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = 'parties.xlsx'
        self.client.force_login(self.accountant)
        self.client.post(reverse('admin_panel:party_import'), {'file': buf})
        imported = Party.objects.get(mobile='09127778899')
        self.assertEqual(imported.party_type, 'supplier')
        self.assertEqual(Party.objects.filter(mobile='09121112233').count(), 1)
