from django.db import models
from django_jalali.db import models as jmodels


class Campaign(models.Model):
    """A templated SMS blast to a filtered segment of parties."""
    name = models.CharField('نام کمپین', max_length=200)
    message = models.TextField('متن پیام', help_text='متغیرها: {name} {mobile} {city}')
    party_type = models.CharField('فیلتر نوع', max_length=10, blank=True,
                                  help_text='خالی = همه')
    tag = models.ForeignKey('parties.PartyTag', on_delete=models.SET_NULL, null=True, blank=True,
                            verbose_name='فیلتر برچسب')
    sent_at = jmodels.jDateTimeField('زمان ارسال', null=True, blank=True)
    sent_count = models.PositiveIntegerField('تعداد ارسال موفق', default=0)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='سازنده')
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'کمپین پیامکی'
        verbose_name_plural = 'کمپین‌های پیامکی'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_sent(self) -> bool:
        return self.sent_at is not None

    @property
    def party_type_label(self) -> str:
        from parties.models import Party
        return dict(Party.TYPE_CHOICES).get(self.party_type, 'همه')


class SMSLog(models.Model):
    """Every outbound SMS (transactional or campaign) is logged here."""
    STATUS_CHOICES = [
        ('sent', 'ارسال شد'),
        ('failed', 'ناموفق'),
    ]
    mobile = models.CharField('موبایل', max_length=11)
    message = models.TextField('متن')
    status = models.CharField('وضعیت', max_length=6, choices=STATUS_CHOICES)
    provider = models.CharField('درگاه', max_length=20, default='console')
    party = models.ForeignKey('parties.Party', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='sms_logs', verbose_name='طرف حساب')
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='logs', verbose_name='کمپین')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='فرستنده')
    created_at = jmodels.jDateTimeField('زمان', auto_now_add=True)

    class Meta:
        verbose_name = 'پیامک ارسالی'
        verbose_name_plural = 'پیامک‌های ارسالی'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.mobile} — {self.get_status_display()}'
