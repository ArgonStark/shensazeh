from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_jalali.db import models as jmodels


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
