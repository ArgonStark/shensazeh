from django.contrib import admin

from .models import SiteSetting


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'phone', 'email', 'updated_at')

    def has_add_permission(self, request):
        # Singleton — block adding extra rows.
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
