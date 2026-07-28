import shutil
import tempfile

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Project, Service


class RichTextRenderTests(TestCase):
    """Service/Project descriptions now hold editor HTML, so the storefront must
    render it rather than escape it — and the project detail page must read the
    field that exists (`description`; it previously read a nonexistent
    `full_description` and showed nothing)."""

    def setUp(self):
        self.body = '<p>متن <strong>پررنگ</strong></p><p><img src="/media/editor/x.jpg"></p>'
        self.service = Service.objects.create(title='مقاوم‌سازی', slug='retrofit-rt',
                                              description=self.body, is_active=True)
        self.project = Project.objects.create(title='پروژه تست', slug='proj-rt',
                                              description=self.body, is_active=True)

    def test_service_detail_renders_html(self):
        r = self.client.get(reverse('services:service_detail', args=[self.service.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '<strong>پررنگ</strong>', html=False)
        self.assertContains(r, '/media/editor/x.jpg')

    def test_project_detail_renders_html(self):
        r = self.client.get(reverse('services:project_detail', args=[self.project.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '<strong>پررنگ</strong>', html=False)

    def test_list_pages_strip_tags_from_teaser(self):
        r = self.client.get(reverse('services:service_list'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, '&lt;p&gt;')
        r = self.client.get(reverse('services:project_list'))
        self.assertNotContains(r, '&lt;p&gt;')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='sazandeh-test-media-'))
class EditorUploadTests(TestCase):
    """The upload endpoint takes a file from a browser, so it trusts the image
    decoder rather than the declared content type or the client's filename.

    MEDIA_ROOT is redirected to a temp dir so the suite never writes into the
    project's real media/ directory.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from accounts.models import User
        from admin_panel.permissions import apply_role_defaults
        self.staff = User.objects.create_user(username='ed', mobile='09120004444',
                                              password='x', is_staff=True)
        apply_role_defaults(self.staff, 'content')
        self.client.force_login(self.staff)
        self.url = reverse('admin_panel:editor_upload')

    def _png(self, name='a.png'):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO()
        Image.new('RGB', (4, 4), 'red').save(buf, format='PNG')
        return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')

    def test_uploads_real_image_and_returns_url(self):
        r = self.client.post(self.url, {'image': self._png()})
        self.assertEqual(r.status_code, 200)
        url = r.json()['url']
        self.assertIn('/editor/', url)
        self.assertTrue(url.endswith('.png'))

    def test_generated_name_ignores_client_filename(self):
        """A client-supplied path must never reach the filesystem."""
        r = self.client.post(self.url, {'image': self._png('../../evil.png')})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('evil', r.json()['url'])
        self.assertNotIn('..', r.json()['url'])

    def test_rejects_non_image_masquerading_as_png(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        payload = SimpleUploadedFile('x.png', b'<?php echo 1; ?>', content_type='image/png')
        r = self.client.post(self.url, {'image': payload})
        self.assertEqual(r.status_code, 400)

    def test_rejects_missing_file(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)

    def test_requires_authoring_permission(self):
        from accounts.models import User
        plain = User.objects.create_user(username='plain', mobile='09120004445',
                                         password='x', is_staff=True)
        self.client.force_login(plain)
        self.assertEqual(self.client.post(self.url, {'image': self._png()}).status_code, 403)

    def test_anonymous_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'image': self._png()}).status_code, 302)


class RichTextPreviewTests(TestCase):
    """List previews show a rich-text body as readable text.

    striptags alone is not enough: it removes the tags but leaves entities like
    &nbsp; behind, which the autoescaper then renders visibly. Quill emits
    plenty of &nbsp;, so both had to be handled.
    """

    def setUp(self):
        self.body = '<p>اجرای&nbsp;تخصصی&nbsp;شاتکریت</p><p>راهکار هوشمندانه</p>'
        self.service = Service.objects.create(title='شاتکریت', slug='shotcrete-pv',
                                              description=self.body, is_active=True)
        Project.objects.create(title='پروژه', slug='proj-pv',
                               description=self.body, is_active=True)

    def test_plain_text_filter_strips_tags_and_entities(self):
        from admin_panel.templatetags.admin_tags import plain_text
        out = plain_text(self.body)
        self.assertNotIn('<p>', out)
        self.assertNotIn('&nbsp;', out)
        self.assertIn('اجرای تخصصی شاتکریت', out)

    def test_plain_text_handles_empty(self):
        from admin_panel.templatetags.admin_tags import plain_text
        self.assertEqual(plain_text(''), '')
        self.assertEqual(plain_text(None), '')

    def test_storefront_service_list_shows_readable_teaser(self):
        html = self.client.get(reverse('services:service_list')).content.decode()
        self.assertNotIn('&lt;p&gt;', html)
        self.assertNotIn('&amp;nbsp;', html)

    def test_storefront_project_list_shows_readable_teaser(self):
        html = self.client.get(reverse('services:project_list')).content.decode()
        self.assertNotIn('&lt;p&gt;', html)
        self.assertNotIn('&amp;nbsp;', html)

    def test_panel_service_list_shows_readable_teaser(self):
        from accounts.models import User
        from admin_panel.permissions import apply_role_defaults
        staff = User.objects.create_user(username='pv', mobile='09120007111',
                                         password='x', is_staff=True)
        apply_role_defaults(staff, 'content')
        self.client.force_login(staff)
        html = self.client.get(reverse('admin_panel:service_list')).content.decode()
        self.assertNotIn('&lt;p&gt;', html)
        self.assertNotIn('&amp;nbsp;', html)
        self.assertIn('اجرای تخصصی شاتکریت', html)

    def test_meta_description_is_clean_text(self):
        """A meta description carrying &nbsp; or markup is what Google shows."""
        html = self.client.get(self.service.get_absolute_url()).content.decode()
        meta = html.split('name="description" content="')[1].split('"')[0]
        self.assertNotIn('&nbsp;', meta)
        self.assertNotIn('<', meta)
        self.assertIn('اجرای تخصصی شاتکریت', meta)


class TemplateCommentTests(TestCase):
    """Django's {# #} comment is single-line only. A two-line one is not a
    comment at all — it renders as literal text on the page."""

    def test_no_multiline_hash_comments_in_templates(self):
        import pathlib
        import re
        offenders = []
        for path in pathlib.Path('.').rglob('*.html'):
            if 'venv' in str(path) or 'staticfiles' in str(path):
                continue
            for num, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                for match in re.finditer(r'\{#', line):
                    if '#}' not in line[match.start():]:
                        offenders.append(f'{path}:{num}')
        self.assertEqual(offenders, [], f'unterminated {{# #}} comments: {offenders}')

    def test_seo_comment_does_not_leak_onto_the_page(self):
        html = self.client.get(reverse('services:service_list')).content.decode()
        self.assertNotIn('Canonical drops the query string', html)
