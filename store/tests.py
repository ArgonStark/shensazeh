from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from blog.models import BlogPost

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


class SEOTests(TestCase):
    """Search engines need a unique description, a canonical URL, and a way to
    discover pages. None of that existed before — only a <title>."""

    def setUp(self):
        self.cat = Category.objects.create(name='ابزار برقی', slug='power-tools-seo')
        self.product = Product.objects.create(name='دریل', slug='drill-seo',
                                              category=self.cat, price=5_000_000)
        self.post = BlogPost.objects.create(title='راهنمای دریل', slug='drill-guide-seo',
                                            content='<p>متن</p>', is_published=True)

    def test_default_head_has_full_seo_set(self):
        r = self.client.get(reverse('home'))
        html = r.content.decode()
        for tag in ('name="description"', 'rel="canonical"', 'property="og:title"',
                    'property="og:image"', 'name="twitter:card"', 'application/ld+json'):
            self.assertIn(tag, html, tag)

    def test_canonical_drops_the_query_string(self):
        """A filtered or paginated variant must not compete with its own base page."""
        r = self.client.get(reverse('store:category_list') + '?sort=price&brand=x')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('rel="canonical" href="http://testserver/store/categories/"', html)
        self.assertNotIn('sort=price', html.split('rel="canonical"')[1][:160])

    def test_meta_title_overrides_fall_back_to_natural_title(self):
        self.assertEqual(self.post.meta_title, '')
        self.assertEqual(self.product.meta_description, '')

    def test_get_absolute_url_resolves(self):
        self.assertEqual(self.post.get_absolute_url(), '/blog/drill-guide-seo/')
        self.assertEqual(self.product.get_absolute_url(), '/store/product/drill-seo/')
        self.assertEqual(self.cat.get_absolute_url(), '/store/category/power-tools-seo/')

    def test_sitemap_lists_published_content(self):
        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        xml = r.content.decode()
        self.assertIn('/blog/drill-guide-seo/', xml)
        self.assertIn('/store/product/drill-seo/', xml)
        self.assertIn('/store/category/power-tools-seo/', xml)

    def test_sitemap_excludes_unpublished_and_inactive(self):
        BlogPost.objects.create(title='پیش‌نویس', slug='draft-seo',
                                content='x', is_published=False)
        Product.objects.create(name='بایگانی', slug='archived-seo',
                               category=self.cat, price=1, is_active=False)
        xml = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn('draft-seo', xml)
        self.assertNotIn('archived-seo', xml)

    def test_robots_txt_blocks_private_areas_and_points_at_sitemap(self):
        r = self.client.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/plain')
        body = r.content.decode()
        self.assertIn('Disallow: /panel/', body)
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)

    def test_page_overrides_reach_the_head(self):
        """Regression: the partial's input names must match what pages pass in.
        A rename once broke this silently — defaults still rendered, so the tags
        looked fine while every page shared the site-wide description."""
        self.post.meta_title = 'عنوان سئوی سفارشی'
        self.post.meta_description = 'توضیح سئوی سفارشی برای گوگل'
        self.post.save()
        html = self.client.get(self.post.get_absolute_url()).content.decode()
        self.assertIn('content="عنوان سئوی سفارشی"', html)
        self.assertIn('توضیح سئوی سفارشی برای گوگل', html)
        self.assertIn('property="og:type" content="article"', html)

    def test_page_without_overrides_falls_back_to_its_own_title(self):
        html = self.client.get(self.post.get_absolute_url()).content.decode()
        self.assertIn('content="راهنمای دریل"', html)
        self.assertNotIn('content="شن‌سازه - ابزار و مصالح ساختمانی"', html)

    def test_product_page_declares_product_og_type(self):
        html = self.client.get(self.product.get_absolute_url()).content.decode()
        self.assertIn('property="og:type" content="product"', html)
        self.assertIn('content="دریل"', html)

    def test_canonical_is_per_page_not_shared(self):
        post_html = self.client.get(self.post.get_absolute_url()).content.decode()
        prod_html = self.client.get(self.product.get_absolute_url()).content.decode()
        self.assertIn('href="http://testserver/blog/drill-guide-seo/"', post_html)
        self.assertIn('href="http://testserver/store/product/drill-seo/"', prod_html)
