from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_jalali.db import models as jmodels


class PartyTag(models.Model):
    name = models.CharField('نام برچسب', max_length=50, unique=True)

    class Meta:
        verbose_name = 'برچسب طرف حساب'
        verbose_name_plural = 'برچسب‌های طرف حساب'
        ordering = ['name']

    def __str__(self):
        return self.name


class Party(models.Model):
    """A customer, supplier, or both — the account holder of a ledger (دفتر حساب)."""
    TYPE_CHOICES = [
        ('customer', 'مشتری'),
        ('supplier', 'تأمین‌کننده'),
        ('both', 'مشتری و تأمین‌کننده'),
    ]
    party_type = models.CharField('نوع', max_length=10, choices=TYPE_CHOICES, default='customer')
    name = models.CharField('نام', max_length=200)
    company = models.CharField('شرکت/فروشگاه', max_length=200, blank=True)
    mobile = models.CharField('موبایل', max_length=11, blank=True)
    phone = models.CharField('تلفن', max_length=30, blank=True)
    national_id = models.CharField('کد/شناسه ملی', max_length=20, blank=True)
    economic_code = models.CharField('کد اقتصادی', max_length=20, blank=True)
    province = models.CharField('استان', max_length=50, blank=True)
    city = models.CharField('شهر', max_length=50, blank=True)
    address = models.TextField('آدرس', blank=True)
    postal_code = models.CharField('کد پستی', max_length=10, blank=True)
    user = models.OneToOneField('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='party', verbose_name='حساب کاربری سایت')
    tags = models.ManyToManyField(PartyTag, blank=True, related_name='parties', verbose_name='برچسب‌ها')
    notes = models.TextField('یادداشت', blank=True)
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'طرف حساب'
        verbose_name_plural = 'طرف حساب‌ها'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.company})' if self.company else self.name

    @property
    def balance(self) -> int:
        """Rial. Positive → the party owes us (بدهکار); negative → we owe them (بستانکار)."""
        totals = self.ledger_entries.aggregate(
            debit=models.Sum('amount', filter=models.Q(entry_type=LedgerEntry.DEBIT), default=0),
            credit=models.Sum('amount', filter=models.Q(entry_type=LedgerEntry.CREDIT), default=0),
        )
        return totals['debit'] - totals['credit']


class LedgerEntry(models.Model):
    """One immutable debit/credit row in a party's account ledger.

    Sign convention (from the shop's perspective):
    - debit  (بدهکار): the party's debt to us increases — e.g. a credit sale.
    - credit (بستانکار): our debt to the party increases / their debt shrinks —
      e.g. a purchase from a supplier, or a payment received from a customer.

    Rows are never edited or deleted; corrections are made with reversing entries.
    """
    DEBIT = 'debit'
    CREDIT = 'credit'
    ENTRY_CHOICES = [
        (DEBIT, 'بدهکار'),
        (CREDIT, 'بستانکار'),
    ]
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='ledger_entries', verbose_name='طرف حساب')
    entry_type = models.CharField('نوع', max_length=6, choices=ENTRY_CHOICES)
    amount = models.PositiveBigIntegerField('مبلغ (ریال)')
    description = models.CharField('شرح', max_length=300)
    # Link to the source document (invoice, payment, cheque, …)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='نوع سند')
    object_id = models.PositiveBigIntegerField('شناسه سند', null=True, blank=True)
    source = GenericForeignKey('content_type', 'object_id')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'سند دفتر حساب'
        verbose_name_plural = 'اسناد دفتر حساب'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['party', 'created_at'])]

    def __str__(self):
        return f'{self.get_entry_type_display()} {self.amount:,} — {self.party.name}'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('اسناد دفتر حساب غیرقابل ویرایش هستند؛ سند اصلاحی ثبت کنید.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('اسناد دفتر حساب غیرقابل حذف هستند؛ سند اصلاحی ثبت کنید.')

    @property
    def signed_amount(self) -> int:
        return self.amount if self.entry_type == self.DEBIT else -self.amount


class Payment(models.Model):
    """A manual receipt from / payment to a party. Writes its ledger entry via
    parties.services.record_payment — never create directly."""
    KIND_CHOICES = [
        ('receipt', 'دریافت از طرف حساب'),
        ('payment', 'پرداخت به طرف حساب'),
    ]
    METHOD_CHOICES = [
        ('cash', 'نقد'),
        ('card', 'کارت به کارت'),
        ('transfer', 'حواله بانکی'),
        ('cheque', 'چک'),
        ('other', 'سایر'),
    ]
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='payments', verbose_name='طرف حساب')
    kind = models.CharField('نوع', max_length=7, choices=KIND_CHOICES)
    method = models.CharField('روش', max_length=10, choices=METHOD_CHOICES, default='cash')
    amount = models.PositiveBigIntegerField('مبلغ (ریال)')
    reference = models.CharField('شماره پیگیری', max_length=100, blank=True)
    description = models.CharField('شرح', max_length=300, blank=True)
    ledger_entry = models.OneToOneField(LedgerEntry, on_delete=models.PROTECT, null=True, editable=False,
                                        related_name='payment', verbose_name='سند دفتر')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'دریافت/پرداخت'
        verbose_name_plural = 'دریافت‌ها و پرداخت‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()} {self.amount:,} ریال — {self.party.name}'
