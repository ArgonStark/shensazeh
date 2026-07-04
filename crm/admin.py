from django.contrib import admin

from .models import Campaign, SMSLog


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'party_type', 'tag', 'sent_at', 'sent_count']


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'mobile', 'status', 'provider', 'party', 'campaign']
    list_filter = ['status', 'provider']
    search_fields = ['mobile', 'message']
