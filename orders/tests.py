import uuid

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.permissions import apply_role_defaults
from finance.money import percent_of
from inventory.models import InventoryEntry
from inventory.services import StockError
from parties.models import LedgerEntry, Party, Payment
from store.models import Category, Product

from .models import Invoice, InvoiceItem, NumberSeries
from .services import InvoiceError, cancel_invoice, issue_invoice, recompute_totals


def make_product(name, price, stock, **kwargs):
    category = Category.objects.first() or Category.objects.create(name='مصالح', slug='materials')
    return Product.objects.create(name=name, slug=name.replace(' ', '-'),
                                  category=category, price=price, stock=stock, **kwargs)


def make_invoice(party, doc_type='sale', items=(), **kwargs):
    invoice = Invoice.objects.create(doc_type=doc_type, party=party, customer_name=party.name, **kwargs)
    for item in items:
        InvoiceItem.objects.create(invoice=invoice, **item)
    return invoice


class TotalsTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='مشتری الف')
        self.product = make_product('سیمان', 1_000_000, 100)

    def test_percent_of_floors(self):
        self.assertEqual(percent_of(1_000_005, 10), 100_000)
        self.assertEqual(percent_of(0, 10), 0)
        self.assertEqual(percent_of(999, 9), 89)

    def test_simple_totals(self):
        invoice = make_invoice(self.party, items=[
            {'product': self.product, 'quantity': 2, 'unit_price': 1_000_000},
        ])
        recompute_totals(invoice)
        self.assertEqual(invoice.subtotal, 2_000_000)
        self.assertEqual(invoice.tax, 0)
        self.assertEqual(invoice.total, 2_000_000)

    def test_line_discount_and_vat(self):
        invoice = make_invoice(self.party, vat_rate=10, items=[
            {'product': self.product, 'quantity': 2, 'unit_price': 1_000_000, 'discount': 200_000},
        ])
        recompute_totals(invoice)
        self.assertEqual(invoice.subtotal, 2_000_000)
        self.assertEqual(invoice.items_discount, 200_000)
        self.assertEqual(invoice.tax, 180_000)  # 10% of 1,800,000
        self.assertEqual(invoice.total, 1_980_000)

    def test_header_discount_allocated_with_remainder(self):
        # Two lines 1,000,000 + 500,000; header discount 1,000 → 666 + 334
        invoice = make_invoice(self.party, vat_rate=10, discount=1_000, items=[
            {'product': self.product, 'quantity': 1, 'unit_price': 1_000_000},
            {'product': self.product, 'quantity': 1, 'unit_price': 500_000},
        ])
        recompute_totals(invoice)
        # taxable = (1,000,000 - 666) + (500,000 - 334) = 1,499,000
        self.assertEqual(invoice.tax, percent_of(1_000_000 - 666, 10) + percent_of(500_000 - 334, 10))
        self.assertEqual(invoice.total, 1_500_000 - 1_000 + invoice.tax)

    def test_per_line_vat_override(self):
        invoice = make_invoice(self.party, vat_rate=10, items=[
            {'product': self.product, 'quantity': 1, 'unit_price': 1_000_000},                # 10%
            {'product': None, 'description': 'اجرت نصب', 'quantity': 1, 'unit_price': 500_000, 'vat_rate': 0},
        ])
        recompute_totals(invoice)
        self.assertEqual(invoice.tax, 100_000)  # only the product line
        self.assertEqual(invoice.total, 1_600_000)

    def test_discount_larger_than_line_rejected(self):
        invoice = make_invoice(self.party, items=[
            {'product': self.product, 'quantity': 1, 'unit_price': 100, 'discount': 200},
        ])
        with self.assertRaises(InvoiceError):
            recompute_totals(invoice)

    def test_header_discount_larger_than_base_rejected(self):
        invoice = make_invoice(self.party, discount=10_000_000, items=[
            {'product': self.product, 'quantity': 1, 'unit_price': 100},
        ])
        with self.assertRaises(InvoiceError):
            recompute_totals(invoice)

    def test_empty_invoice_rejected(self):
        invoice = make_invoice(self.party)
        with self.assertRaises(InvoiceError):
            recompute_totals(invoice)


class IssueFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='acc', mobile='09120003000', password='x', is_staff=True)
        self.party = Party.objects.create(name='بنّای محله', mobile='09121110000')
        self.product = make_product('گچ ساوه', 800_000, 50)

    def _sale(self, qty=10, **kwargs):
        return make_invoice(self.party, items=[
            {'product': self.product, 'quantity': qty, 'unit_price': 800_000},
        ], **kwargs)

    def test_issue_sale_full_effects(self):
        invoice = self._sale(settlement_type='credit')
        issue_invoice(invoice, self.user)
        invoice.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(invoice.status, 'issued')
        self.assertTrue(invoice.invoice_number.startswith('S-'))
        self.assertEqual(self.product.stock, 40)
        movement = InventoryEntry.objects.get(entry_type='out')
        self.assertEqual(movement.reference, invoice.invoice_number)
        entry = LedgerEntry.objects.get(party=self.party)
        self.assertEqual(entry.entry_type, LedgerEntry.DEBIT)
        self.assertEqual(entry.amount, 8_000_000)
        self.assertEqual(self.party.balance, 8_000_000)
        self.assertFalse(invoice.is_paid)

    def test_cash_settlement_marks_paid_and_records_receipt(self):
        invoice = self._sale(settlement_type='cash', paid_amount=8_000_000)
        issue_invoice(invoice, self.user)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_paid)
        self.assertEqual(self.party.balance, 0)  # debit 8M + receipt credit 8M
        payment = Payment.objects.get()
        self.assertEqual(payment.kind, 'receipt')
        self.assertEqual(payment.amount, 8_000_000)

    def test_partial_settlement(self):
        invoice = self._sale(settlement_type='partial', paid_amount=3_000_000)
        issue_invoice(invoice, self.user)
        invoice.refresh_from_db()
        self.assertFalse(invoice.is_paid)
        self.assertEqual(invoice.remaining_amount, 5_000_000)
        self.assertEqual(self.party.balance, 5_000_000)

    def test_overpay_rejected(self):
        invoice = self._sale(settlement_type='partial', paid_amount=9_000_000)
        with self.assertRaises(InvoiceError):
            issue_invoice(invoice, self.user)

    def test_oversell_rolls_back_everything(self):
        invoice = self._sale(qty=60)
        with self.assertRaises(StockError):
            issue_invoice(invoice, self.user)
        invoice.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(invoice.status, 'draft')
        self.assertTrue(invoice.invoice_number.startswith('DRAFT-'))
        self.assertEqual(self.product.stock, 50)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(InventoryEntry.objects.count(), 0)

    def test_purchase_updates_stock_and_cost_and_credits_party(self):
        supplier = Party.objects.create(name='پخش مصالح', party_type='supplier')
        invoice = make_invoice(supplier, doc_type='purchase', items=[
            {'product': self.product, 'quantity': 20, 'unit_price': 600_000},
        ])
        invoice = issue_invoice(invoice, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 70)
        self.assertEqual(self.product.purchase_price, 600_000)
        self.assertTrue(invoice.invoice_number.startswith('B-'))
        self.assertEqual(supplier.balance, -12_000_000)  # we owe them

    def test_sale_return_restocks_and_credits(self):
        invoice = make_invoice(self.party, doc_type='sale_return', items=[
            {'product': self.product, 'quantity': 5, 'unit_price': 800_000},
        ])
        issue_invoice(invoice, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 55)
        self.assertEqual(self.party.balance, -4_000_000)

    def test_proforma_has_no_financial_effect(self):
        invoice = self._sale()
        invoice.doc_type = 'proforma'
        invoice.save(update_fields=['doc_type'])
        issue_invoice(invoice, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 50)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertTrue(Invoice.objects.get(pk=invoice.pk).invoice_number.startswith('PF-'))

    def test_service_line_skips_stock(self):
        invoice = make_invoice(self.party, items=[
            {'product': None, 'description': 'حمل با نیسان', 'quantity': 1, 'unit_price': 2_000_000},
        ])
        issue_invoice(invoice, self.user)
        self.assertEqual(InventoryEntry.objects.count(), 0)
        self.assertEqual(self.party.balance, 2_000_000)

    def test_number_series_increments(self):
        first = issue_invoice(self._sale(), self.user)
        second = issue_invoice(self._sale(), self.user)
        self.assertEqual(first.invoice_number, 'S-00001')
        self.assertEqual(second.invoice_number, 'S-00002')
        self.assertEqual(NumberSeries.objects.get(doc_type='sale').next_number, 3)

    def test_issue_twice_rejected(self):
        invoice = self._sale()
        issue_invoice(invoice, self.user)
        with self.assertRaises(InvoiceError):
            issue_invoice(invoice, self.user)

    def test_cancel_reverses_stock_and_ledger(self):
        invoice = self._sale(settlement_type='credit')
        issue_invoice(invoice, self.user)
        cancel_invoice(invoice, self.user)
        invoice.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(invoice.status, 'cancelled')
        self.assertEqual(self.product.stock, 50)
        self.assertEqual(self.party.balance, 0)
        self.assertEqual(InventoryEntry.objects.filter(entry_type='return_in').count(), 1)

    def test_cancel_draft_rejected(self):
        invoice = self._sale()
        with self.assertRaises(InvoiceError):
            cancel_invoice(invoice, self.user)


class InvoicePanelViewTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username='sale1', mobile='09120003001', password='x', is_staff=True)
        apply_role_defaults(self.seller, 'sales')
        self.party = Party.objects.create(name='مشتری پنل', mobile='09122223344')
        self.product = make_product('میلگرد ۱۴', 5_000_000, 30)
        self.client.force_login(self.seller)

    def _post_data(self, action='issue', token=None, **overrides):
        data = {
            'submission_token': token or str(uuid.uuid4()),
            'action': action,
            'doc_type': 'sale',
            'party_id': str(self.party.pk),
            'item_product': [str(self.product.pk)],
            'item_description': [''],
            'item_qty': ['3'],
            'item_price': ['5000000'],
            'item_discount': ['0'],
            'item_vat': [''],
            'discount': '0',
            'vat_rate': '10',
            'settlement_type': 'credit',
            'paid_amount': '0',
            'due_date': '1405/06/01',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_create_and_issue_via_panel(self):
        response = self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.status, 'issued')
        self.assertEqual(invoice.total, 15_000_000 + 1_500_000)  # + 10% VAT
        self.assertEqual(invoice.due_date.year, 1405)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 27)

    def test_double_submit_same_token_is_idempotent(self):
        token = str(uuid.uuid4())
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data(token=token))
        response = self.client.post(reverse('admin_panel:invoice_create'), self._post_data(token=token))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Invoice.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 27)  # stock moved once

    def test_draft_then_issue(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data(action='draft'))
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.status, 'draft')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 30)  # drafts have no effect
        self.client.post(reverse('admin_panel:invoice_issue', args=[invoice.pk]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'issued')

    def test_issued_invoice_not_editable(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        invoice = Invoice.objects.get()
        original_total = invoice.total
        response = self.client.post(reverse('admin_panel:invoice_edit', args=[invoice.pk]),
                                    self._post_data(**{'item_price': ['1']}))
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, original_total)

    def test_sales_role_cannot_cancel(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        invoice = Invoice.objects.get()
        response = self.client.post(reverse('admin_panel:invoice_cancel', args=[invoice.pk]))
        self.assertEqual(response.status_code, 403)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'issued')

    def test_quick_create_party(self):
        data = self._post_data(party_id='new')
        data['new_party_name'] = 'مشتری گذری'
        data['new_party_mobile'] = '09125550000'
        self.client.post(reverse('admin_panel:invoice_create'), data)
        self.assertTrue(Party.objects.filter(name='مشتری گذری', mobile='09125550000').exists())

    def test_validation_error_rerenders_form(self):
        response = self.client.post(reverse('admin_panel:invoice_create'),
                                    self._post_data(**{'item_qty': ['0']}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_detail_page_renders_issued_invoice(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        invoice = Invoice.objects.get()
        response = self.client.get(reverse('admin_panel:invoice_detail', args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, invoice.invoice_number)
        self.assertContains(response, 'صادر شده')

    def test_form_page_renders(self):
        response = self.client.get(reverse('admin_panel:invoice_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'اقلام سند')

    def test_export_excel(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        response = self.client.get(reverse('admin_panel:invoice_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

    def test_list_filters_by_type_and_query(self):
        self.client.post(reverse('admin_panel:invoice_create'), self._post_data())
        response = self.client.get(reverse('admin_panel:invoice_list'), {'type': 'sale', 'q': 'S-'})
        self.assertContains(response, 'S-00001')
        response = self.client.get(reverse('admin_panel:invoice_list'), {'type': 'purchase'})
        self.assertNotContains(response, 'S-00001')
