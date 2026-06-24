from django.contrib import admin

from .models import SiteVisit


@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'path', 'user', 'visited_at')
    list_filter = ('visited_at',)
    search_fields = ('ip_address', 'path', 'user__mobile', 'user__first_name')
    raw_id_fields = ('user',)
    readonly_fields = ('ip_address', 'path', 'user_agent', 'user', 'visited_at')
    ordering = ('-visited_at',)
