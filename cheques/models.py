from django.db import models
from django_jalali.db import models as jmodels

from finance.words import rial_to_words


class ChequeBook(models.Model):
    """A cheque book of our own account (source of issued cheques)."""
    bank_name = models.CharField('بانک', max_length=100)
    branch = models.CharField('شعبه', max_length=100, blank=True)
    account_number = models.CharField('شماره حساب', max_length=30, blank=True)
    serial_from = models.CharField('سریال اول', max_length=30, blank=True)
    serial_to = models.CharField('سریال آخر', max_length=30, blank=True)
    notes = models.TextField('توضیحات', blank=True)
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'دسته‌چک'
        verbose_name_plural = 'دسته‌چک‌ها'
        ordering = ['-created_at']

    def __str__(self):
        label = f'{self.bank_name} {self.branch}'.strip()
        return f'دسته‌چک {label} ({self.account_number})' if self.account_number else f'دسته‌چک {label}'


class Cheque(models.Model):
    """A received or issued cheque.

    Lifecycle: pending → cleared | bounced (final). The party ledger is only
    posted when the cheque clears (cheques.services.set_cheque_status);
    a pending cheque is a promise, not money.
    """
    DIRECTION_CHOICES = [
        ('received', 'دریافتی'),
        ('issued', 'پرداختی'),
    ]
    STATUS_CHOICES = [
        ('pending', 'در جریان وصول'),
        ('cleared', 'وصول شده'),
        ('bounced', 'برگشت خورده'),
    ]
    direction = models.CharField('نوع', max_length=8, choices=DIRECTION_CHOICES)
    status = models.CharField('وضعیت', max_length=8, choices=STATUS_CHOICES, default='pending')
    party = models.ForeignKey('parties.Party', on_delete=models.PROTECT, related_name='cheques', verbose_name='طرف حساب')
    invoice = models.ForeignKey('orders.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='cheques', verbose_name='فاکتور مرتبط')
    cheque_book = models.ForeignKey(ChequeBook, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='cheques', verbose_name='دسته‌چک')
    serial = models.CharField('شماره چک', max_length=30)
    sayad_id = models.CharField('شناسه صیادی', max_length=16, blank=True)
    bank_name = models.CharField('بانک', max_length=100)
    branch = models.CharField('شعبه', max_length=100, blank=True)
    amount = models.PositiveBigIntegerField('مبلغ (ریال)')
    due_date = jmodels.jDateField('تاریخ سررسید')
    payee = models.CharField('در وجه', max_length=200, blank=True)
    description = models.CharField('شرح', max_length=300, blank=True)
    status_changed_at = jmodels.jDateTimeField('تاریخ تغییر وضعیت', null=True, blank=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'چک'
        verbose_name_plural = 'چک‌ها'
        ordering = ['due_date']
        indexes = [models.Index(fields=['status', 'due_date'])]

    def __str__(self):
        return f'چک {self.serial} — {self.get_direction_display()} {self.amount:,} ریال'

    @property
    def amount_words(self) -> str:
        return rial_to_words(self.amount)

    @property
    def is_overdue(self) -> bool:
        import jdatetime
        return self.status == 'pending' and self.due_date < jdatetime.date.today()


class ChequePrintLayout(models.Model):
    """Per-bank print offsets (millimetres from the cheque's top-right corner)."""
    bank_name = models.CharField('بانک', max_length=100, unique=True)
    paper_width = models.PositiveSmallIntegerField('عرض چک (میلی‌متر)', default=165)
    paper_height = models.PositiveSmallIntegerField('ارتفاع چک (میلی‌متر)', default=80)
    date_x = models.PositiveSmallIntegerField('تاریخ — فاصله از راست', default=25)
    date_y = models.PositiveSmallIntegerField('تاریخ — فاصله از بالا', default=10)
    amount_x = models.PositiveSmallIntegerField('مبلغ عددی — فاصله از راست', default=110)
    amount_y = models.PositiveSmallIntegerField('مبلغ عددی — فاصله از بالا', default=25)
    words_x = models.PositiveSmallIntegerField('مبلغ حروفی — فاصله از راست', default=25)
    words_y = models.PositiveSmallIntegerField('مبلغ حروفی — فاصله از بالا', default=38)
    payee_x = models.PositiveSmallIntegerField('در وجه — فاصله از راست', default=30)
    payee_y = models.PositiveSmallIntegerField('در وجه — فاصله از بالا', default=52)

    class Meta:
        verbose_name = 'قالب چاپ چک'
        verbose_name_plural = 'قالب‌های چاپ چک'
        ordering = ['bank_name']

    def __str__(self):
        return f'قالب چاپ {self.bank_name}'
