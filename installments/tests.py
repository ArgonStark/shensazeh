import jdatetime
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.permissions import apply_role_defaults
from orders.models import Invoice, InvoiceItem
from orders.services import issue_invoice
from parties.models import LedgerEntry, Party
from store.models import Category, Product

from .models import Installment, InstallmentPlan
from .services import (InstallmentError, add_jalali_months, build_schedule,
                       create_installment_plan, pay_installment)


class JalaliMonthTests(TestCase):
    def test_simple_step(self):
        self.assertEqual(add_jalali_months(jdatetime.date(1404, 1, 15), 1), jdatetime.date(1404, 2, 15))

    def test_day_clamped_to_short_month(self):
        # 31 Shahrivar + 1 month → Mehr has 30 days
        self.assertEqual(add_jalali_months(jdatetime.date(1404, 6, 31), 1), jdatetime.date(1404, 7, 30))

    def test_year_rollover(self):
        self.assertEqual(add_jalali_months(jdatetime.date(1404, 11, 10), 3), jdatetime.date(1405, 2, 10))

    def test_esfand_leap_handling(self):
        # 1403 is a leap year (Esfand has 30 days)
        self.assertEqual(add_jalali_months(jdatetime.date(1403, 11, 30), 1), jdatetime.date(1403, 12, 30))


class ScheduleTests(TestCase):
    def test_none_method_splits_exactly(self):
        interest, amounts = build_schedule(10_000_000, 'none', 0, 3)
        self.assertEqual(interest, 0)
        self.assertEqual(sum(amounts), 10_000_000)
        self.assertEqual(amounts, [3_333_333, 3_333_333, 3_333_334])

    def test_simple_interest_formula(self):
        # I = P × r/100 × n/12 = 12,000,000 × 0.24 × 0.5 = 1,440,000
        interest, amounts = build_schedule(12_000_000, 'simple', 24, 6)
        self.assertEqual(interest, 1_440_000)
        self.assertEqual(sum(amounts), 13_440_000)
        self.assertEqual(len(amounts), 6)

    def test_reducing_balance_sums_exactly(self):
        interest, amounts = build_schedule(12_000_000, 'reducing', 24, 6)
        self.assertEqual(sum(amounts), 12_000_000 + interest)
        # Reducing interest must be less than simple for the same terms
        simple_interest, _ = build_schedule(12_000_000, 'simple', 24, 6)
        self.assertLess(interest, simple_interest)
        self.assertGreater(interest, 0)
        # All but the last payment are equal
        self.assertEqual(len(set(amounts[:-1])), 1)

    def test_validation(self):
        with self.assertRaises(InstallmentError):
            build_schedule(0, 'none', 0, 3)
        with self.assertRaises(InstallmentError):
            build_schedule(100, 'none', 0, 0)
        with self.assertRaises(InstallmentError):
            build_schedule(100, 'simple', 0, 3)  # rate required
        with self.assertRaises(InstallmentError):
            build_schedule(100, 'magic', 10, 3)


class PlanFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='inst', mobile='09120006000', password='x', is_staff=True)
        self.party = Party.objects.create(name='خریدار قسطی')
        category = Category.objects.create(name='مصالح', slug='materials')
        self.product = Product.objects.create(name='تیرآهن', slug='beam', category=category,
                                              price=10_000_000, stock=50)
        invoice = Invoice.objects.create(doc_type='sale', party=self.party, customer_name=self.party.name,
                                         settlement_type='credit')
        InvoiceItem.objects.create(invoice=invoice, product=self.product, quantity=2, unit_price=10_000_000)
        self.invoice = issue_invoice(invoice, self.user)
        self.start = jdatetime.date.today() + jdatetime.timedelta(days=30)

    def test_create_plan_posts_interest_debit(self):
        plan = create_installment_plan(self.invoice, method='simple', annual_rate=24,
                                       count=4, start_date=self.start, user=self.user)
        self.assertEqual(plan.principal, 20_000_000)
        self.assertEqual(plan.total_interest, (20_000_000 * 24 * 4) // 1200)
        self.assertEqual(plan.installments.count(), 4)
        # party owes invoice total + interest
        self.assertEqual(self.party.balance, 20_000_000 + plan.total_interest)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.settlement_type, 'installment')

    def test_no_duplicate_plan(self):
        create_installment_plan(self.invoice, method='none', annual_rate=0,
                                count=2, start_date=self.start, user=self.user)
        self.invoice.refresh_from_db()
        with self.assertRaises(InstallmentError):
            create_installment_plan(self.invoice, method='none', annual_rate=0,
                                    count=2, start_date=self.start, user=self.user)

    def test_plan_requires_issued_sale(self):
        draft = Invoice.objects.create(doc_type='sale', party=self.party, customer_name='x')
        with self.assertRaises(InstallmentError):
            create_installment_plan(draft, method='none', annual_rate=0,
                                    count=2, start_date=self.start, user=self.user)

    def test_past_start_date_rejected(self):
        with self.assertRaises(InstallmentError):
            create_installment_plan(self.invoice, method='none', annual_rate=0, count=2,
                                    start_date=jdatetime.date.today() - jdatetime.timedelta(days=1),
                                    user=self.user)

    def test_pay_installment_flow(self):
        plan = create_installment_plan(self.invoice, method='none', annual_rate=0,
                                       count=2, start_date=self.start, user=self.user)
        first, second = plan.installments.all()
        balance_before = self.party.balance

        pay_installment(first, first.amount, self.user)
        first.refresh_from_db()
        self.assertTrue(first.is_paid)
        self.assertEqual(self.party.balance, balance_before - first.amount)

        # overpay second rejected
        with self.assertRaises(InstallmentError):
            pay_installment(second, second.amount + 1, self.user)

        pay_installment(second, second.amount, self.user)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_paid)
        plan = InstallmentPlan.objects.get(pk=plan.pk)
        self.assertTrue(plan.is_settled)

    def test_partial_payment(self):
        plan = create_installment_plan(self.invoice, method='none', annual_rate=0,
                                       count=1, start_date=self.start, user=self.user)
        installment = plan.installments.get()
        pay_installment(installment, 5_000_000, self.user)
        installment.refresh_from_db()
        self.assertFalse(installment.is_paid)
        self.assertEqual(installment.remaining, 15_000_000)


class InstallmentPanelTests(TestCase):
    def setUp(self):
        self.accountant = User.objects.create_user(username='ia', mobile='09120006001', password='x', is_staff=True)
        apply_role_defaults(self.accountant, 'accountant')
        self.party = Party.objects.create(name='پیمانکار')
        category = Category.objects.create(name='ابزار', slug='tools')
        product = Product.objects.create(name='دریل', slug='drill', category=category,
                                         price=30_000_000, stock=5)
        invoice = Invoice.objects.create(doc_type='sale', party=self.party, customer_name=self.party.name,
                                         settlement_type='credit')
        InvoiceItem.objects.create(invoice=invoice, product=product, quantity=1, unit_price=30_000_000)
        self.invoice = issue_invoice(invoice, self.accountant)
        self.client.force_login(self.accountant)

    def test_create_plan_via_panel(self):
        start = (jdatetime.date.today() + jdatetime.timedelta(days=10)).strftime('%Y/%m/%d')
        response = self.client.post(
            reverse('admin_panel:installment_plan_create', args=[self.invoice.pk]),
            {'method': 'reducing', 'annual_rate': '30', 'count': '5', 'start_date': start})
        self.assertEqual(response.status_code, 302)
        plan = InstallmentPlan.objects.get()
        self.assertEqual(plan.count, 5)
        self.assertGreater(plan.total_interest, 0)

    def test_list_and_detail_render(self):
        start = jdatetime.date.today() + jdatetime.timedelta(days=5)
        plan = create_installment_plan(self.invoice, method='none', annual_rate=0,
                                       count=3, start_date=start, user=self.accountant)
        self.assertEqual(self.client.get(reverse('admin_panel:installment_list')).status_code, 200)
        response = self.client.get(reverse('admin_panel:installment_plan_detail', args=[plan.pk]))
        self.assertContains(response, self.invoice.invoice_number)

    def test_pay_endpoint(self):
        start = jdatetime.date.today() + jdatetime.timedelta(days=5)
        plan = create_installment_plan(self.invoice, method='none', annual_rate=0,
                                       count=3, start_date=start, user=self.accountant)
        installment = plan.installments.first()
        self.client.post(reverse('admin_panel:installment_pay', args=[installment.pk]),
                         {'amount': installment.amount, 'method': 'card'})
        installment.refresh_from_db()
        self.assertTrue(installment.is_paid)
