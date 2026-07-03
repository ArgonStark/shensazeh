from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_jalali.db import models as jmodels


class InventoryEntry(models.Model):
    """One immutable row in the stock ledger (کاردکس).

    Current stock derives from this ledger; `Product.stock` is a cached value
    that inventory.services.record_movement keeps in sync inside a
    transaction. Rows are never edited or deleted — corrections are recorded
    as compensating movements. Do not create rows directly; use the service.
    """
    ENTRY_TYPE_CHOICES = [
        ('in', 'ورود کالا'),
        ('out', 'خروج کالا'),
        ('return_in', 'برگشت به انبار'),
        ('return_out', 'برگشت از انبار'),
        ('adjust', 'اصلاح موجودی'),
    ]
    INBOUND_TYPES = ('in', 'return_in')
    product = models.ForeignKey('store.Product', on_delete=models.PROTECT, related_name='inventory_entries', verbose_name='محصول')
    entry_type = models.CharField('نوع', max_length=10, choices=ENTRY_TYPE_CHOICES)
    quantity = models.PositiveIntegerField('تعداد')
    unit_cost = models.PositiveBigIntegerField('قیمت واحد (ریال)', default=0)
    balance_after = models.PositiveIntegerField('موجودی پس از حرکت', default=0)
    supplier = models.CharField('تأمین‌کننده', max_length=200, blank=True)
    reference = models.CharField('شماره مرجع', max_length=100, blank=True)
    notes = models.TextField('توضیحات', blank=True)
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='inventory_entries', verbose_name='سفارش مرتبط')
    # Source document (invoice, adjustment, …)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='نوع سند')
    object_id = models.PositiveBigIntegerField('شناسه سند', null=True, blank=True)
    source = GenericForeignKey('content_type', 'object_id')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'حرکت انبار'
        verbose_name_plural = 'حرکت‌های انبار (کاردکس)'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['product', 'created_at'])]

    def __str__(self):
        return f'{self.get_entry_type_display()} - {self.product.name} ({self.quantity})'

    @property
    def is_inbound(self) -> bool:
        return self.entry_type in self.INBOUND_TYPES

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.is_inbound else -self.quantity

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('حرکت‌های انبار غیرقابل ویرایش هستند؛ حرکت اصلاحی ثبت کنید.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('حرکت‌های انبار غیرقابل حذف هستند؛ حرکت اصلاحی ثبت کنید.')
