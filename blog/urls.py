from django.urls import path

from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.BlogListView.as_view(), name='blog_list'),
    path('announcements/', views.AnnouncementListView.as_view(), name='announcement_list'),
    path('ai-assist/', views.AIAssistView.as_view(), name='ai_assist'),
    path('<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
    path('<slug:slug>/comment/', views.BlogCommentCreateView.as_view(), name='blog_comment_create'),
]
