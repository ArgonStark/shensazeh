from django.contrib import admin

from .models import Cheque, ChequeBook, ChequePrintLayout


@admin.register(Cheque)
class ChequeAdmin(admin.ModelAdmin):
    list_display = ['serial', 'direction', 'status', 'party', 'amount', 'due_date']
    list_filter = ['direction', 'status', 'bank_name']
    search_fields = ['serial', 'sayad_id', 'party__name']


@admin.register(ChequeBook)
class ChequeBookAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'branch', 'account_number', 'is_active']


@admin.register(ChequePrintLayout)
class ChequePrintLayoutAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'paper_width', 'paper_height']
