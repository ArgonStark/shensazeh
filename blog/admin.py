from django.contrib import admin

from .models import BlogPost, BlogComment, Announcement


class BlogCommentInline(admin.StackedInline):
    model = BlogComment
    extra = 0
    readonly_fields = ('created_at',)
    verbose_name = 'نظر'
    verbose_name_plural = 'نظرات'


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_published', 'views_count', 'created_at', 'updated_at')
    list_filter = ('is_published', 'created_at', 'author')
    search_fields = ('title', 'slug', 'content', 'excerpt')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    readonly_fields = ('views_count', 'created_at', 'updated_at')
    list_editable = ('is_published',)
    inlines = [BlogCommentInline]
    ordering = ('-created_at',)


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('post__title', 'user__mobile', 'user__first_name', 'text')
    raw_id_fields = ('post', 'user')
    readonly_fields = ('created_at',)
    actions = ['approve_comments']

    @admin.action(description='تأیید نظرات انتخاب شده')
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'content')
    list_editable = ('is_active',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
