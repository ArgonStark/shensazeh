from django.contrib import admin

from .models import LedgerEntry, Party, PartyTag, Payment


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ['name', 'party_type', 'mobile', 'city', 'is_active']
    list_filter = ['party_type', 'is_active', 'tags']
    search_fields = ['name', 'company', 'mobile', 'national_id']


@admin.register(PartyTag)
class PartyTagAdmin(admin.ModelAdmin):
    search_fields = ['name']


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'party', 'entry_type', 'amount', 'description']
    list_filter = ['entry_type']
    search_fields = ['party__name', 'description']

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'party', 'kind', 'method', 'amount']
    list_filter = ['kind', 'method']
    search_fields = ['party__name', 'reference']
