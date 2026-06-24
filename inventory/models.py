from django.db import models
from django_jalali.db import models as jmodels


class InventoryEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('in', 'ورود کالا'),
        ('out', 'خروج کالا'),
    ]
    product = models.ForeignKey('store.Product', on_delete=models.PROTECT, related_name='inventory_entries', verbose_name='محصول')
    entry_type = models.CharField('نوع', max_length=3, choices=ENTRY_TYPE_CHOICES)
    quantity = models.PositiveIntegerField('تعداد')
    supplier = models.CharField('تأمین‌کننده', max_length=200, blank=True)
    reference = models.CharField('شماره مرجع', max_length=100, blank=True)
    notes = models.TextField('توضیحات', blank=True)
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='inventory_entries', verbose_name='سفارش مرتبط')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'ورودی/خروجی انبار'
        verbose_name_plural = 'ورودی/خروجی‌های انبار'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_entry_type_display()} - {self.product.name} ({self.quantity})'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            if self.entry_type == 'in':
                self.product.stock += self.quantity
            else:
                self.product.stock = max(0, self.product.stock - self.quantity)
            self.product.save(update_fields=['stock'])
