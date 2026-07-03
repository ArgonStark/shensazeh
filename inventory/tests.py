from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.permissions import apply_role_defaults
from finance.models import AuditLog
from store.models import Category, Product

from .models import InventoryEntry
from .services import StockError, record_movement


def make_product(name='سیمان تیپ ۲', stock=0, **kwargs):
    category = Category.objects.first() or Category.objects.create(name='مصالح', slug='materials')
    defaults = {'price': 1_000_000, 'reorder_point': 5}
    defaults.update(kwargs)
    return Product.objects.create(
        name=name, slug=name.replace(' ', '-'), category=category, stock=stock, **defaults)


class RecordMovementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='wh1', mobile='09120002000', password='x', is_staff=True)
        self.product = make_product(stock=10)

    def test_inbound_increases_stock_and_writes_balance(self):
        entry = record_movement(self.product, 'in', 5, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)
        self.assertEqual(entry.balance_after, 15)
        self.assertTrue(AuditLog.objects.filter(action='create', object_id=entry.pk).exists())

    def test_outbound_decreases_stock(self):
        entry = record_movement(self.product, 'out', 4, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertEqual(entry.balance_after, 6)

    def test_oversell_rejected(self):
        with self.assertRaises(StockError):
            record_movement(self.product, 'out', 11, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(InventoryEntry.objects.count(), 0)

    def test_oversell_allowed_when_flagged_floors_at_zero(self):
        entry = record_movement(self.product, 'out', 11, user=self.user, allow_negative=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(entry.balance_after, 0)

    def test_return_types_move_correct_direction(self):
        record_movement(self.product, 'return_in', 3, user=self.user)   # sale return comes back in
        record_movement(self.product, 'return_out', 2, user=self.user)  # purchase return goes out
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 11)

    def test_bad_quantity_and_type_rejected(self):
        for bad_qty in (0, -3, 'x', None):
            with self.assertRaises(StockError):
                record_movement(self.product, 'in', bad_qty)
        with self.assertRaises(StockError):
            record_movement(self.product, 'teleport', 1)

    def test_inbound_with_unit_cost_updates_purchase_price(self):
        record_movement(self.product, 'in', 5, unit_cost=800_000, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, 800_000)
        self.assertEqual(self.product.profit_per_unit, 200_000)

    def test_entries_are_immutable(self):
        entry = record_movement(self.product, 'in', 1)
        entry.quantity = 99
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()


class ProductModelTests(TestCase):
    def test_auto_code_generated(self):
        product = make_product(name='چکش مهندسی')
        self.assertEqual(product.code, f'P{product.pk:05d}')

    def test_manual_code_kept(self):
        product = make_product(name='متر لیزری', code='TOOL-77')
        self.assertEqual(product.code, 'TOOL-77')

    def test_low_stock_uses_reorder_point(self):
        low = make_product(name='کم', stock=3, reorder_point=5)
        ok = make_product(name='زیاد', stock=30, reorder_point=5)
        self.assertTrue(low.is_low_stock)
        self.assertFalse(ok.is_low_stock)
        low_qs = Product.objects.filter(stock__gt=0, stock__lte=F('reorder_point'))
        self.assertIn(low, low_qs)
        self.assertNotIn(ok, low_qs)


class InventoryPanelTests(TestCase):
    def setUp(self):
        self.wh = User.objects.create_user(username='wh2', mobile='09120002001', password='x', is_staff=True)
        apply_role_defaults(self.wh, 'warehouse')
        self.product = make_product(stock=8)
        self.client.force_login(self.wh)

    def test_create_movement_via_panel(self):
        response = self.client.post(reverse('admin_panel:inventory_create'), {
            'product': self.product.pk, 'entry_type': 'in', 'quantity': 12,
            'unit_cost': 900000, 'supplier': 'بازرگانی فارس', 'reference': '', 'notes': '',
        })
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 20)
        self.assertEqual(self.product.purchase_price, 900000)

    def test_oversell_via_panel_shows_error(self):
        response = self.client.post(reverse('admin_panel:inventory_create'), {
            'product': self.product.pk, 'entry_type': 'out', 'quantity': 100,
            'unit_cost': '', 'supplier': '', 'reference': '', 'notes': '',
        })
        self.assertEqual(response.status_code, 200)  # re-rendered with error
        self.assertContains(response, 'کافی نیست')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_kardex_page(self):
        record_movement(self.product, 'in', 2, user=self.wh)
        response = self.client.get(reverse('admin_panel:product_kardex', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'کاردکس')

    def test_product_stock_locked_on_edit_form(self):
        from admin_panel.forms import ProductForm
        form = ProductForm(instance=self.product, data={
            'name': self.product.name, 'slug': self.product.slug, 'code': self.product.code,
            'category': self.product.category.pk, 'unit': 'عدد', 'price': 1, 'purchase_price': 0,
            'stock': 9999, 'reorder_point': 5, 'is_active': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['stock'], 8)  # posted 9999 ignored


class ProductExcelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='mgr', mobile='09120002002', password='x', is_staff=True)
        apply_role_defaults(self.admin, 'manager')
        self.client.force_login(self.admin)
        self.product = make_product(name='آجر سفال', code='BRICK-1', stock=100)

    def test_export(self):
        response = self.client.get(reverse('admin_panel:product_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

    def test_import_updates_by_code_but_not_stock(self):
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['کد کالا', 'نام', 'دسته‌بندی', 'واحد', 'قیمت فروش', 'قیمت خرید', 'نقطه سفارش', 'بارکد'])
        ws.append(['BRICK-1', 'آجر سفال درجه یک', '', 'عدد', 2_500_000, 2_000_000, 20, ''])
        ws.append(['', 'ماسه شسته', '', 'کیسه', 400_000, 300_000, 10, ''])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = 'products.xlsx'
        self.client.post(reverse('admin_panel:product_import'), {'file': buf})
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'آجر سفال درجه یک')
        self.assertEqual(self.product.price, 2_500_000)
        self.assertEqual(self.product.stock, 100)  # untouched
        new = Product.objects.get(name='ماسه شسته')
        self.assertEqual(new.unit, 'کیسه')
        self.assertEqual(new.stock, 0)
