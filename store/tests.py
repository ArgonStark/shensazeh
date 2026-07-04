from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.forms import (BlogPostForm, CategoryForm, ProductForm,
                               ProjectForm, ServiceForm)
from store.models import Category, Product


class ProductPanelRenderTests(TestCase):
    """The create/edit pages must render — regression for the unguarded
    form.instance.images.all() on an unsaved product (Django 6 ValueError)."""

    def setUp(self):
        self.cat = Category.objects.create(name='ابزار', slug='tools-r')
        self.staff = User.objects.create_user(username='r', mobile='09990010001', password='x', is_staff=True)
        for cn in ['add_product', 'change_product', 'view_product']:
            self.staff.user_permissions.add(
                Permission.objects.get(content_type__app_label='store', codename=cn))
        self.client.force_login(self.staff)

    def test_create_page_renders(self):
        response = self.client.get(reverse('admin_panel:product_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'افزودن محصول')

    def test_edit_page_renders(self):
        product = Product.objects.create(name='چکش', slug='hammer-r', category=self.cat, price=100000)
        response = self.client.get(reverse('admin_panel:product_edit', args=[product.pk]))
        self.assertEqual(response.status_code, 200)


class ProductFormTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name='ابزار برقی', slug='power-tools')

    def _base(self, **overrides):
        data = {
            'name': 'دریل شارژی', 'slug': '', 'code': '', 'category': str(self.cat.id),
            'description': 'توضیح', 'unit': 'عدد', 'price': '8500000', 'purchase_price': '7000000',
            'barcode': '', 'stock': '15', 'reorder_point': '5', 'is_active': 'on',
            'specs': '', 'expiry_date': '',
        }
        data.update(overrides)
        return data

    def test_blank_slug_autogenerates(self):
        form = ProductForm(self._base())
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.slug, 'دریل-شارژی')

    def test_duplicate_name_gets_unique_slug(self):
        ProductForm(self._base()).save()
        product2 = ProductForm(self._base()).save()
        self.assertEqual(product2.slug, 'دریل-شارژی-2')

    def test_specs_plaintext_parsed_to_dict(self):
        form = ProductForm(self._base(specs='ولتاژ: ۱۸ ولت\nوزن: ۲ کیلوگرم\nبدون مقدار'))
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.specifications,
                         {'ولتاژ': '۱۸ ولت', 'وزن': '۲ کیلوگرم', 'بدون مقدار': ''})

    def test_jalali_expiry_parsed(self):
        form = ProductForm(self._base(expiry_date='1405/06/01'))
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.expiry_date.year, 1405)

    def test_bad_expiry_rejected(self):
        form = ProductForm(self._base(expiry_date='فردا'))
        self.assertFalse(form.is_valid())
        self.assertIn('expiry_date', form.errors)

    def test_category_required(self):
        form = ProductForm(self._base(category=''))
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_edit_keeps_slug_and_locks_stock(self):
        product = ProductForm(self._base()).save()
        form = ProductForm(self._base(name='دریل شارژی', stock='999'), instance=product)
        self.assertTrue(form.is_valid(), form.errors)
        edited = form.save()
        self.assertEqual(edited.stock, 15)  # stock field disabled on edit


class AutoSlugFormTests(TestCase):
    def test_blog_service_project_category_autoslug(self):
        blog = BlogPostForm({'title': 'راهنمای خرید سیمان', 'slug': '', 'content': 'x',
                             'excerpt': '', 'is_published': ''})
        self.assertTrue(blog.is_valid(), blog.errors)
        self.assertEqual(blog.save(commit=False).slug, 'راهنمای-خرید-سیمان')

        service = ServiceForm({'title': 'نصب', 'slug': '', 'description': 'x', 'icon': '', 'order': '0'})
        self.assertTrue(service.is_valid(), service.errors)

        project = ProjectForm({'title': 'پروژه برج', 'slug': '', 'description': 'x',
                               'client': '', 'location': ''})
        self.assertTrue(project.is_valid(), project.errors)

        category = CategoryForm({'name': 'مصالح', 'slug': '', 'order': '0'})
        self.assertTrue(category.is_valid(), category.errors)

    def test_explicit_slug_is_slugified_not_overwritten(self):
        form = CategoryForm({'name': 'مصالح ساختمانی', 'slug': 'building materials', 'order': '0'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['slug'], 'building-materials')
