from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_jalali.db import models as jmodels


class ExpenseCategory(models.Model):
    KIND_CHOICES = [
        ('expense', 'هزینه'),
        ('income', 'درآمد'),
    ]
    name = models.CharField('نام دسته', max_length=100)
    kind = models.CharField('نوع', max_length=7, choices=KIND_CHOICES, default='expense')
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        verbose_name = 'دسته هزینه/درآمد'
        verbose_name_plural = 'دسته‌های هزینه/درآمد'
        ordering = ['kind', 'name']
        unique_together = ['name', 'kind']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.name}'


class CashTransaction(models.Model):
    """Income/expense outside buy-sell documents (rent, utilities, transport …)."""
    KIND_CHOICES = ExpenseCategory.KIND_CHOICES
    kind = models.CharField('نوع', max_length=7, choices=KIND_CHOICES)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT,
                                 related_name='transactions', verbose_name='دسته')
    amount = models.PositiveBigIntegerField('مبلغ (ریال)')
    date = jmodels.jDateField('تاریخ')
    description = models.CharField('شرح', max_length=300, blank=True)
    reference = models.CharField('شماره مرجع', max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, verbose_name='ثبت‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'تراکنش هزینه/درآمد'
        verbose_name_plural = 'هزینه‌ها و درآمدها'
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['kind', 'date'])]

    def __str__(self):
        return f'{self.get_kind_display()} {self.amount:,} — {self.category.name}'

    @property
    def signed_amount(self) -> int:
        return self.amount if self.kind == 'income' else -self.amount


class AuditLog(models.Model):
    """Immutable record of a financial/administrative mutation.

    Rows are only ever created (via finance.audit.log_action) — never edited.
    """
    ACTION_CHOICES = [
        ('create', 'ایجاد'),
        ('update', 'ویرایش'),
        ('delete', 'حذف'),
        ('status', 'تغییر وضعیت'),
    ]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='audit_logs', verbose_name='کاربر')
    action = models.CharField('عملیات', max_length=10, choices=ACTION_CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, verbose_name='نوع رکورد')
    object_id = models.PositiveBigIntegerField('شناسه رکورد')
    content_object = GenericForeignKey('content_type', 'object_id')
    object_repr = models.CharField('عنوان رکورد', max_length=200)
    changes = models.JSONField('تغییرات', default=dict, blank=True)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'رویداد حسابرسی'
        verbose_name_plural = 'رویدادهای حسابرسی'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return f'{self.get_action_display()} {self.object_repr}'
