from django.db import models
from django_jalali.db import models as jmodels


class SiteVisit(models.Model):
    ip_address = models.GenericIPAddressField('آدرس IP')
    path = models.CharField('مسیر', max_length=500)
    user_agent = models.TextField('مرورگر', blank=True)
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='کاربر')
    visited_at = jmodels.jDateTimeField('تاریخ بازدید', auto_now_add=True)

    class Meta:
        verbose_name = 'بازدید'
        verbose_name_plural = 'بازدیدها'
        ordering = ['-visited_at']

    def __str__(self):
        return f'{self.ip_address} - {self.path}'
