from django.contrib import admin

from .models import Installment, InstallmentPlan


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0


@admin.register(InstallmentPlan)
class InstallmentPlanAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'party', 'method', 'count', 'total_payable', 'start_date']
    list_filter = ['method']
    search_fields = ['invoice__invoice_number', 'party__name']
    inlines = [InstallmentInline]
