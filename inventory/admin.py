from django.contrib import admin

from .models import InventoryEntry


@admin.register(InventoryEntry)
class InventoryEntryAdmin(admin.ModelAdmin):
    list_display = ('product', 'entry_type', 'quantity', 'supplier', 'reference', 'created_by', 'created_at')
    list_filter = ('entry_type', 'created_at', 'supplier')
    search_fields = ('product__name', 'supplier', 'reference', 'notes')
    raw_id_fields = ('product', 'order', 'created_by')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
