from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import BlogComment, BlogPost


class BlogDetailCommentRenderTests(TestCase):
    """The comment byline used `{{ comment.user.get_full_name|default:comment.user.phone }}`.

    accounts.User has no `phone` field — it is `mobile` — and because Django
    resolves filter *arguments* eagerly without swallowing
    VariableDoesNotExist, the post page 500'd on any approved comment,
    regardless of whether the commenter had a full name set.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='commenter', mobile='09120007777',
                                             password='x')
        self.post = BlogPost.objects.create(title='مقاله تست', slug='test-post',
                                            content='متن مقاله', is_published=True,
                                            author=self.user)

    def _url(self):
        return reverse('blog:blog_detail', args=[self.post.slug])

    def test_detail_renders_with_approved_comment(self):
        BlogComment.objects.create(post=self.post, user=self.user,
                                   text='نظر تست', is_approved=True)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'نظر تست')

    def test_byline_falls_back_to_mobile_when_no_full_name(self):
        BlogComment.objects.create(post=self.post, user=self.user,
                                   text='نظر بدون نام', is_approved=True)
        response = self.client.get(self._url())
        self.assertContains(response, self.user.mobile)

    def test_byline_prefers_full_name(self):
        self.user.first_name, self.user.last_name = 'سارا', 'محمدی'
        self.user.save()
        BlogComment.objects.create(post=self.post, user=self.user,
                                   text='نظر با نام', is_approved=True)
        response = self.client.get(self._url())
        self.assertContains(response, 'سارا محمدی')

    def test_detail_renders_without_comments(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_comment_body_and_date_are_visible(self):
        """`{{ comment.content }}` / `{{ comment.jalali_date }}` named fields
        that do not exist, so bodies and dates rendered blank."""
        comment = BlogComment.objects.create(post=self.post, user=self.user,
                                             text='متن قابل مشاهده', is_approved=True)
        response = self.client.get(self._url())
        self.assertContains(response, 'متن قابل مشاهده')
        self.assertContains(response, comment.created_at.strftime('%Y/%m/%d'))

    def test_unapproved_comment_is_hidden(self):
        BlogComment.objects.create(post=self.post, user=self.user,
                                   text='نظر تاییدنشده', is_approved=False)
        response = self.client.get(self._url())
        self.assertNotContains(response, 'نظر تاییدنشده')
