from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import StaffProfile, User
from finance.models import AuditLog
from orders.models import Invoice, Order
from store.models import Category, Product

from . import permissions as panel_permissions


def grant(user, *perm_labels):
    for label in perm_labels:
        app, codename = label.split('.')
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app, codename=codename))


class PanelPermissionMixinTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='s1', mobile='09120000010', password='x', is_staff=True)
        self.customer = User.objects.create_user(username='c1', mobile='09120000011', password='x')

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('admin_panel:product_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_non_staff_gets_403(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('admin_panel:product_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_without_permission_gets_403(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_panel:product_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_with_permission_gets_200(self):
        grant(self.staff, 'store.view_product')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_panel:product_list'))
        self.assertEqual(response.status_code, 200)

    def test_view_permission_does_not_grant_delete(self):
        grant(self.staff, 'store.view_product')
        category = Category.objects.create(name='ابزار', slug='tools')
        product = Product.objects.create(name='چکش', slug='hammer', category=category, price=100000)
        self.client.force_login(self.staff)
        response = self.client.post(reverse('admin_panel:product_delete', args=[product.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_superuser_passes_everything(self):
        boss = User.objects.create_superuser(username='b', mobile='09120000012', password='x')
        self.client.force_login(boss)
        self.assertEqual(self.client.get(reverse('admin_panel:product_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin_panel:audit_list')).status_code, 200)


class RoleDefaultsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='w1', mobile='09120000020', password='x', is_staff=True)

    def test_warehouse_defaults(self):
        panel_permissions.apply_role_defaults(self.user, 'warehouse')
        self.assertTrue(self.user.has_perm('inventory.add_inventoryentry'))
        self.assertTrue(self.user.has_perm('store.view_product'))
        self.assertTrue(self.user.has_perm('orders.view_invoice'))
        self.assertFalse(self.user.has_perm('orders.delete_invoice'))
        self.assertFalse(self.user.has_perm('store.add_product'))

    def test_sales_cannot_delete_invoices(self):
        panel_permissions.apply_role_defaults(self.user, 'sales')
        self.assertTrue(self.user.has_perm('orders.add_invoice'))
        self.assertTrue(self.user.has_perm('orders.change_invoice'))
        self.assertFalse(self.user.has_perm('orders.delete_invoice'))

    def test_manager_gets_everything_including_audit_view(self):
        panel_permissions.apply_role_defaults(self.user, 'manager')
        self.assertTrue(self.user.has_perm('finance.view_auditlog'))
        self.assertTrue(self.user.has_perm('admin_panel.change_sitesetting'))
        self.assertTrue(self.user.has_perm('accounts.change_user'))

    def test_reapplying_role_resets_extra_grants(self):
        grant(self.user, 'orders.delete_invoice')
        panel_permissions.apply_role_defaults(self.user, 'content')
        self.user = User.objects.get(pk=self.user.pk)
        self.assertFalse(self.user.has_perm('orders.delete_invoice'))
        self.assertTrue(self.user.has_perm('blog.add_blogpost'))


class StaffManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='m1', mobile='09120000030', password='x', is_staff=True)
        panel_permissions.apply_role_defaults(self.admin, 'manager')
        self.client.force_login(self.admin)

    def test_staff_create_applies_role_defaults(self):
        self.client.post(reverse('admin_panel:staff_create'),
                         {'mobile': '09120000031', 'role': 'warehouse'})
        created = User.objects.get(mobile='09120000031')
        self.assertTrue(created.is_staff)
        self.assertTrue(created.has_perm('inventory.add_inventoryentry'))
        self.assertEqual(created.staff_profile.role, 'warehouse')
        self.assertTrue(AuditLog.objects.filter(action='create').exists())

    def test_permissions_matrix_grants_and_revokes(self):
        self.client.post(reverse('admin_panel:staff_create'),
                         {'mobile': '09120000032', 'role': 'sales'})
        seller = User.objects.get(mobile='09120000032')
        sp = seller.staff_profile
        self.assertTrue(seller.has_perm('orders.add_invoice'))

        # Revoke everything except products:view
        response = self.client.post(
            reverse('admin_panel:staff_permissions', args=[sp.pk]), {'products:view': 'on'})
        self.assertEqual(response.status_code, 302)
        seller = User.objects.get(pk=seller.pk)
        self.assertTrue(seller.has_perm('store.view_product'))
        self.assertFalse(seller.has_perm('orders.add_invoice'))
        log = AuditLog.objects.filter(action='update', object_id=seller.pk).latest('id')
        self.assertIn('permissions', log.changes)

    def test_matrix_page_renders(self):
        self.client.post(reverse('admin_panel:staff_create'),
                         {'mobile': '09120000034', 'role': 'sales'})
        sp = User.objects.get(mobile='09120000034').staff_profile
        response = self.client.get(reverse('admin_panel:staff_permissions', args=[sp.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'فاکتورها')

    def test_staff_delete_deactivates_and_logs(self):
        self.client.post(reverse('admin_panel:staff_create'),
                         {'mobile': '09120000033', 'role': 'content'})
        sp = User.objects.get(mobile='09120000033').staff_profile
        self.client.post(reverse('admin_panel:staff_delete', args=[sp.pk]))
        sp.refresh_from_db()
        self.assertFalse(sp.is_active_staff)
        self.assertFalse(sp.user.is_staff)
        self.assertTrue(AuditLog.objects.filter(action='status', object_id=sp.pk).exists())


class DashboardTests(TestCase):
    def test_dashboard_renders_finance_widgets(self):
        boss = User.objects.create_superuser(username='dash', mobile='09120000060', password='x')
        self.client.force_login(boss)
        response = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'طلب و بدهی')
        self.assertContains(response, 'چک‌های نزدیک سررسید')


class InvoiceAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='a1', mobile='09120000040', password='x', is_staff=True)
        panel_permissions.apply_role_defaults(self.admin, 'manager')
        self.customer = User.objects.create_user(username='c2', mobile='09120000041', password='x')
        order = Order.objects.create(customer=self.customer)
        self.invoice = Invoice.objects.create(order=order, customer_name='تست', subtotal=1000, total=1000)

    def test_invoice_delete_writes_audit_row(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_panel:invoice_delete', args=[self.invoice.pk]))
        self.assertFalse(Invoice.objects.filter(pk=self.invoice.pk).exists())
        log = AuditLog.objects.filter(action='delete').latest('id')
        self.assertEqual(log.changes['before']['customer_name'], 'تست')
        self.assertEqual(log.actor, self.admin)


class InvoiceDetailAccessTests(TestCase):
    """orders.InvoiceDetailView: staff with permission or the owning customer only."""

    def setUp(self):
        self.owner = User.objects.create_user(username='o1', mobile='09120000050', password='x')
        self.other = User.objects.create_user(username='o2', mobile='09120000051', password='x')
        self.staff = User.objects.create_user(username='o3', mobile='09120000052', password='x', is_staff=True)
        order = Order.objects.create(customer=self.owner)
        self.invoice = Invoice.objects.create(order=order, customer_name='مالک', subtotal=1, total=1)
        self.url = reverse('orders:invoice_detail', kwargs={'pk': self.invoice.pk})

    def test_anonymous_redirected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_other_customer_gets_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_owner_can_view(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_staff_with_permission_can_view(self):
        grant(self.staff, 'orders.view_invoice')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_staff_without_permission_gets_404(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)
