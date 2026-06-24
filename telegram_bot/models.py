from django.db import models
from django_jalali.db import models as jmodels


class TelegramMessage(models.Model):
    product = models.ForeignKey('store.Product', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='محصول')
    message_text = models.TextField('متن پیام')
    message_id = models.CharField('شناسه پیام تلگرام', max_length=50, blank=True)
    is_sent = models.BooleanField('ارسال شده', default=False)
    error_message = models.TextField('خطا', blank=True)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'پیام تلگرام'
        verbose_name_plural = 'پیام‌های تلگرام'
        ordering = ['-created_at']

    def __str__(self):
        return f'پیام {self.pk} - {"ارسال شده" if self.is_sent else "ارسال نشده"}'
