from django.contrib import admin

from .models import TelegramMessage


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'product', 'is_sent', 'message_id', 'created_at')
    list_filter = ('is_sent', 'created_at')
    search_fields = ('message_text', 'product__name', 'message_id', 'error_message')
    raw_id_fields = ('product',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
