import anthropic
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, DetailView, CreateView

from .models import BlogPost, BlogComment, Announcement


class BlogListView(ListView):
    """Paginated list of published posts."""
    model = BlogPost
    template_name = 'blog/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True).select_related('author')


class BlogDetailView(DetailView):
    """Single blog post. Increments views_count on each visit."""
    model = BlogPost
    template_name = 'blog/blog_detail.html'
    context_object_name = 'post'
    slug_field = 'slug'

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True).select_related('author')

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Increment views_count
        BlogPost.objects.filter(pk=self.object.pk).update(
            views_count=self.object.views_count + 1
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.comments.filter(is_approved=True)
        return context


class BlogCommentCreateView(LoginRequiredMixin, CreateView):
    """POST to add a comment on a blog post."""
    model = BlogComment
    fields = ['text']
    template_name = 'blog/comment_form.html'

    def form_valid(self, form):
        post = get_object_or_404(BlogPost, slug=self.kwargs['slug'], is_published=True)
        form.instance.user = self.request.user
        form.instance.post = post
        form.save()
        return redirect(reverse('blog:blog_detail', kwargs={'slug': post.slug}))


class AnnouncementListView(ListView):
    """List active announcements."""
    model = Announcement
    template_name = 'blog/announcement_list.html'
    context_object_name = 'announcements'
    paginate_by = 10

    def get_queryset(self):
        return Announcement.objects.filter(is_active=True)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class AIAssistView(StaffRequiredMixin, View):
    """Staff only: POST with a prompt, call Anthropic API to generate blog content."""

    def post(self, request):
        prompt = request.POST.get('prompt', '').strip()
        if not prompt:
            return JsonResponse({'error': 'متن درخواست الزامی است.'}, status=400)

        try:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=2048,
                messages=[
                    {
                        'role': 'user',
                        'content': (
                            f'لطفاً یک مقاله وبلاگ به فارسی بنویسید درباره موضوع زیر. '
                            f'مقاله باید شامل عنوان، خلاصه و محتوای کامل باشد.\n\n'
                            f'موضوع: {prompt}'
                        ),
                    }
                ],
            )
            content = message.content[0].text
            return JsonResponse({'content': content})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
