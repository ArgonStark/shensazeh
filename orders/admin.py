from django.contrib import admin

from .models import Order, OrderItem, Invoice, InvoiceItem


class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 1
    raw_id_fields = ('product',)
    verbose_name = 'آیتم سفارش'
    verbose_name_plural = 'آیتم‌های سفارش'


class InvoiceItemInline(admin.StackedInline):
    model = InvoiceItem
    extra = 1
    raw_id_fields = ('product',)
    verbose_name = 'آیتم فاکتور'
    verbose_name_plural = 'آیتم‌های فاکتور'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'status', 'total_amount', 'discount', 'tax', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'customer__mobile', 'customer__first_name', 'customer__last_name', 'notes')
    raw_id_fields = ('customer',)
    readonly_fields = ('order_number', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
    ordering = ('-created_at',)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'unit_price')
    list_filter = ('order__status',)
    search_fields = ('order__order_number', 'product__name')
    raw_id_fields = ('order', 'product')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order', 'customer_name', 'customer_mobile', 'subtotal', 'discount', 'tax', 'total', 'is_paid', 'created_at')
    list_filter = ('is_paid', 'created_at')
    search_fields = ('invoice_number', 'customer_name', 'customer_mobile', 'order__order_number', 'notes')
    raw_id_fields = ('order',)
    readonly_fields = ('invoice_number', 'created_at', 'updated_at')
    inlines = [InvoiceItemInline]
    ordering = ('-created_at',)


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'product', 'description', 'quantity', 'unit_price')
    search_fields = ('invoice__invoice_number', 'product__name', 'description')
    raw_id_fields = ('invoice', 'product')
