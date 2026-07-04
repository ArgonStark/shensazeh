import jdatetime
from django.db import models
from django_jalali.db import models as jmodels


class InstallmentPlan(models.Model):
    """Installment schedule attached to an issued sale invoice.

    Interest methods (see installments.services.build_schedule for the exact
    integer-Rial implementation):

    - none      → I = 0
    - simple    → I = P × r/100 × n/12  (annual rate r over an n-month term)
    - reducing  → equal amortized payments on the declining balance:
                  A = P·i·(1+i)ⁿ / ((1+i)ⁿ − 1), monthly i = r/1200
    """
    METHOD_CHOICES = [
        ('none', 'بدون سود'),
        ('simple', 'سود ساده سالانه'),
        ('reducing', 'سود بر مانده (اقساط مساوی)'),
    ]
    invoice = models.OneToOneField('orders.Invoice', on_delete=models.PROTECT,
                                   related_name='installment_plan', verbose_name='فاکتور')
    party = models.ForeignKey('parties.Party', on_delete=models.PROTECT,
                              related_name='installment_plans', verbose_name='طرف حساب')
    principal = models.PositiveBigIntegerField('اصل مبلغ (ریال)')
    method = models.CharField('روش سود', max_length=8, choices=METHOD_CHOICES, default='none')
    annual_rate = models.PositiveSmallIntegerField('نرخ سود سالانه (٪)', default=0)
    count = models.PositiveSmallIntegerField('تعداد اقساط')
    total_interest = models.PositiveBigIntegerField('جمع سود (ریال)', default=0)
    total_payable = models.PositiveBigIntegerField('جمع قابل پرداخت (ریال)', default=0)
    start_date = jmodels.jDateField('سررسید قسط اول')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'طرح اقساط'
        verbose_name_plural = 'طرح‌های اقساط'
        ordering = ['-created_at']

    def __str__(self):
        return f'اقساط {self.invoice.invoice_number} — {self.count} قسط'

    @property
    def paid_total(self) -> int:
        return sum(i.paid_amount for i in self.installments.all())

    @property
    def remaining(self) -> int:
        return max(0, self.total_payable - self.paid_total)

    @property
    def is_settled(self) -> bool:
        return self.remaining == 0


class Installment(models.Model):
    plan = models.ForeignKey(InstallmentPlan, on_delete=models.CASCADE,
                             related_name='installments', verbose_name='طرح')
    seq = models.PositiveSmallIntegerField('شماره قسط')
    due_date = jmodels.jDateField('سررسید')
    amount = models.PositiveBigIntegerField('مبلغ قسط (ریال)')
    paid_amount = models.PositiveBigIntegerField('پرداخت‌شده (ریال)', default=0)
    paid_at = jmodels.jDateTimeField('تاریخ تسویه', null=True, blank=True)

    class Meta:
        verbose_name = 'قسط'
        verbose_name_plural = 'اقساط'
        ordering = ['plan', 'seq']
        unique_together = ['plan', 'seq']
        indexes = [models.Index(fields=['due_date'])]

    def __str__(self):
        return f'قسط {self.seq} از {self.plan}'

    @property
    def remaining(self) -> int:
        return max(0, self.amount - self.paid_amount)

    @property
    def is_paid(self) -> bool:
        return self.paid_amount >= self.amount

    @property
    def is_overdue(self) -> bool:
        return not self.is_paid and self.due_date < jdatetime.date.today()
