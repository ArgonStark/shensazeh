from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import StaffProfile, User
from admin_panel.models import SiteSetting
from admin_panel.permissions import apply_role_defaults
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


class AIProviderTests(TestCase):
    """The assistant dispatches to whichever provider the panel is set to, and
    every failure path returns a Persian message rather than a raw exception."""

    def setUp(self):
        self.site = SiteSetting.load()

    def test_missing_anthropic_key_is_reported(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'anthropic'
        self.site.anthropic_api_key = ''
        with override_settings(ANTHROPIC_API_KEY=''):
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        self.assertIn('کلید API کلاد', str(ctx.exception))

    def test_missing_openai_key_is_reported(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'openai'
        self.site.openai_api_key = ''
        with self.assertRaises(AIError) as ctx:
            generate_article('تست', site=self.site)
        self.assertIn('اوپن‌ای‌آی', str(ctx.exception))

    def test_unknown_provider_is_reported(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'nonesuch'
        with self.assertRaises(AIError):
            generate_article('تست', site=self.site)

    def test_openai_reads_choice_text(self):
        from admin_panel.ai import generate_article
        self.site.ai_provider = 'openai'
        self.site.openai_api_key = 'sk-test'
        payload = {'choices': [{'message': {'content': ' متن تولید شده '}}]}
        with patch('httpx.post', return_value=Mock(status_code=200, json=lambda: payload)):
            self.assertEqual(generate_article('تست', site=self.site), 'متن تولید شده')

    def test_openai_bad_key_maps_to_message(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'openai'
        self.site.openai_api_key = 'sk-bad'
        with patch('httpx.post', return_value=Mock(status_code=401, json=lambda: {})):
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        self.assertIn('معتبر نیست', str(ctx.exception))

    def test_openai_unreadable_body_maps_to_message(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'openai'
        self.site.openai_api_key = 'sk-test'
        with patch('httpx.post', return_value=Mock(status_code=200, json=lambda: {'unexpected': 1})):
            with self.assertRaises(AIError):
                generate_article('تست', site=self.site)

    def test_anthropic_refusal_maps_to_message(self):
        from admin_panel.ai import AIError, generate_article
        self.site.ai_provider = 'anthropic'
        self.site.anthropic_api_key = 'sk-ant-test'
        reply = Mock(stop_reason='refusal', content=[])
        with patch('anthropic.Anthropic') as client:
            client.return_value.messages.create.return_value = reply
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        self.assertIn('رد شد', str(ctx.exception))

    def test_anthropic_returns_text(self):
        from admin_panel.ai import generate_article
        self.site.ai_provider = 'anthropic'
        self.site.anthropic_api_key = 'sk-ant-test'
        block = Mock(type='text', text='مقاله')
        reply = Mock(stop_reason='end_turn', content=[block])
        with patch('anthropic.Anthropic') as client:
            client.return_value.messages.create.return_value = reply
            self.assertEqual(generate_article('تست', site=self.site), 'مقاله')


class AIAssistViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='aiuser', mobile='09120005555',
                                              password='x', is_staff=True)
        apply_role_defaults(self.staff, 'content')
        self.client.force_login(self.staff)
        self.url = reverse('admin_panel:ai_assist')

    def test_empty_prompt_rejected(self):
        r = self.client.post(self.url, {'prompt': '  '})
        self.assertEqual(r.status_code, 400)

    def test_provider_error_surfaces_persian_message(self):
        with patch('admin_panel.ai.generate_article',
                   side_effect=__import__('admin_panel.ai', fromlist=['AIError']).AIError('کلید نیست')):
            r = self.client.post(self.url, {'prompt': 'دریل'})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()['error'], 'کلید نیست')

    def test_unexpected_error_does_not_leak_detail(self):
        """An internal fault must not put its exception text in the browser."""
        with patch('admin_panel.ai.generate_article',
                   side_effect=RuntimeError('sk-ant-secret-leaked')):
            r = self.client.post(self.url, {'prompt': 'دریل'})
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('secret', r.json()['error'])


class OpenRouterProviderTests(TestCase):
    """OpenRouter fronts ~370 models behind an OpenAI-shaped endpoint."""

    def setUp(self):
        self.site = SiteSetting.load()
        self.site.ai_provider = 'openrouter'
        self.site.openrouter_api_key = 'sk-or-test'
        self.site.openrouter_model = 'anthropic/claude-opus-5'

    def _ok(self, content='متن مقاله'):
        return Mock(status_code=200,
                    json=lambda: {'choices': [{'message': {'content': content}}]})

    def test_missing_key_is_reported(self):
        from admin_panel.ai import AIError, generate_article
        self.site.openrouter_api_key = ''
        with self.assertRaises(AIError) as ctx:
            generate_article('تست', site=self.site)
        self.assertIn('اوپن‌روتر', str(ctx.exception))

    def test_returns_content(self):
        from admin_panel.ai import generate_article
        with patch('httpx.post', return_value=self._ok()):
            self.assertEqual(generate_article('تست', site=self.site), 'متن مقاله')

    def test_sends_selected_model_and_attribution_headers(self):
        from admin_panel.ai import generate_article
        with patch('httpx.post', return_value=self._ok()) as post:
            generate_article('تست', site=self.site)
        body = post.call_args.kwargs['json']
        headers = post.call_args.kwargs['headers']
        self.assertEqual(body['model'], 'anthropic/claude-opus-5')
        self.assertEqual(headers['Authorization'], 'Bearer sk-or-test')
        self.assertIn('X-Title', headers)

    def test_web_search_tools_only_sent_when_enabled(self):
        from admin_panel.ai import generate_article
        with patch('httpx.post', return_value=self._ok()) as post:
            generate_article('تست', site=self.site)
        self.assertNotIn('tools', post.call_args.kwargs['json'])

        self.site.openrouter_web_search = True
        with patch('httpx.post', return_value=self._ok()) as post:
            generate_article('تست', site=self.site)
        tools = post.call_args.kwargs['json']['tools']
        self.assertEqual([t['type'] for t in tools],
                         ['openrouter:web_search', 'openrouter:web_fetch'])

    def test_upstream_error_returned_as_200_is_surfaced(self):
        """OpenRouter reports provider failures as HTTP 200 with an error object."""
        from admin_panel.ai import AIError, generate_article
        payload = {'error': {'message': 'model is overloaded'}}
        with patch('httpx.post', return_value=Mock(status_code=200, json=lambda: payload)):
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        self.assertIn('overloaded', str(ctx.exception))

    def test_no_credit_maps_to_message(self):
        from admin_panel.ai import AIError, generate_article
        with patch('httpx.post', return_value=Mock(status_code=402, json=lambda: {})):
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        self.assertIn('اعتبار', str(ctx.exception))

    def test_null_content_maps_to_message(self):
        from admin_panel.ai import AIError, generate_article
        payload = {'choices': [{'message': {'content': None}}]}
        with patch('httpx.post', return_value=Mock(status_code=200, json=lambda: payload)):
            with self.assertRaises(AIError):
                generate_article('تست', site=self.site)


class OpenRouterModelListTests(TestCase):
    CATALOGUE = {'data': [
        {'id': 'anthropic/claude-opus-5', 'name': 'Claude Opus 5', 'context_length': 1000000,
         'pricing': {'prompt': '0.000005', 'completion': '0.000025'},
         'supported_parameters': ['tools']},
        {'id': 'free/model', 'name': 'Free Model', 'context_length': 8192,
         'pricing': {'prompt': '0', 'completion': '0'}, 'supported_parameters': []},
    ]}

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_per_token_pricing_converted_to_per_million(self):
        from admin_panel.ai import openrouter_models
        with patch('httpx.get', return_value=Mock(status_code=200, raise_for_status=lambda: None,
                                                  json=lambda: self.CATALOGUE)):
            models = openrouter_models()
        opus = next(m for m in models if m['id'] == 'anthropic/claude-opus-5')
        self.assertEqual((opus['in'], opus['out']), (5.0, 25.0))
        self.assertTrue(opus['tools'])
        self.assertFalse(next(m for m in models if m['id'] == 'free/model')['tools'])

    def test_result_is_cached_so_the_picker_does_not_refetch(self):
        from admin_panel.ai import openrouter_models
        with patch('httpx.get', return_value=Mock(status_code=200, raise_for_status=lambda: None,
                                                  json=lambda: self.CATALOGUE)) as get:
            openrouter_models()
            openrouter_models()
        self.assertEqual(get.call_count, 1)

    def test_fetch_failure_raises_persian_error(self):
        import httpx
        from admin_panel.ai import AIError, openrouter_models
        with patch('httpx.get', side_effect=httpx.ConnectError('boom')):
            with self.assertRaises(AIError):
                openrouter_models()

    def test_endpoint_requires_settings_permission(self):
        url = reverse('admin_panel:openrouter_models')
        staff = User.objects.create_user(username='norights', mobile='09120006666',
                                         password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_endpoint_returns_models(self):
        url = reverse('admin_panel:openrouter_models')
        boss = User.objects.create_user(username='boss', mobile='09120006667',
                                        password='x', is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        with patch('httpx.get', return_value=Mock(status_code=200, raise_for_status=lambda: None,
                                                  json=lambda: self.CATALOGUE)):
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['models']), 2)


class AIProxyTests(TestCase):
    """OpenRouter answers this project's server with 403 while Anthropic and
    OpenAI answer it normally, so the proxy is the difference between that
    provider being usable and not."""

    def setUp(self):
        self.site = SiteSetting.load()
        self.site.openrouter_api_key = 'sk-or-test'
        self.site.ai_provider = 'openrouter'

    def _ok(self):
        return Mock(status_code=200,
                    json=lambda: {'choices': [{'message': {'content': 'متن'}}]})

    def test_no_proxy_configured_sends_none(self):
        from admin_panel.ai import generate_article
        with patch('httpx.post', return_value=self._ok()) as post:
            generate_article('تست', site=self.site)
        self.assertIsNone(post.call_args.kwargs['proxy'])

    def test_configured_proxy_is_used(self):
        from admin_panel.ai import generate_article
        self.site.ai_proxy_url = '  http://127.0.0.1:8118  '
        with patch('httpx.post', return_value=self._ok()) as post:
            generate_article('تست', site=self.site)
        self.assertEqual(post.call_args.kwargs['proxy'], 'http://127.0.0.1:8118')

    def test_403_explains_the_ip_block_rather_than_the_status_code(self):
        from admin_panel.ai import AIError, generate_article
        with patch('httpx.post', return_value=Mock(status_code=403, json=lambda: {})):
            with self.assertRaises(AIError) as ctx:
                generate_article('تست', site=self.site)
        message = str(ctx.exception)
        self.assertIn('مسدود', message)
        self.assertIn('پراکسی', message)

    def test_model_list_403_explains_the_ip_block(self):
        from admin_panel.ai import AIError, openrouter_models
        from django.core.cache import cache
        cache.clear()
        with patch('httpx.get', return_value=Mock(status_code=403)):
            with self.assertRaises(AIError) as ctx:
                openrouter_models()
        self.assertIn('مسدود', str(ctx.exception))

    def test_anthropic_routes_through_proxy_when_set(self):
        from admin_panel.ai import generate_article
        self.site.ai_provider = 'anthropic'
        self.site.anthropic_api_key = 'sk-ant-test'
        self.site.ai_proxy_url = 'http://127.0.0.1:8118'
        block = Mock(type='text', text='مقاله')
        reply = Mock(stop_reason='end_turn', content=[block])
        with patch('anthropic.Anthropic') as client, patch('anthropic.DefaultHttpxClient') as http:
            client.return_value.messages.create.return_value = reply
            generate_article('تست', site=self.site)
        http.assert_called_once_with(proxy='http://127.0.0.1:8118')
