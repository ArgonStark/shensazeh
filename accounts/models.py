from django.contrib.auth.models import AbstractUser
from django.db import models
from django_jalali.db import models as jmodels


class User(AbstractUser):
    mobile = models.CharField('شماره موبایل', max_length=11, unique=True)
    province = models.CharField('استان', max_length=50, blank=True)
    city = models.CharField('شهر', max_length=50, blank=True)
    address = models.TextField('آدرس', blank=True)
    postal_code = models.CharField('کد پستی', max_length=10, blank=True)
    created_at = jmodels.jDateTimeField('تاریخ عضویت', auto_now_add=True)

    USERNAME_FIELD = 'mobile'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'

    def __str__(self):
        return self.get_full_name() or self.mobile


class OTPCode(models.Model):
    mobile = models.CharField('شماره موبایل', max_length=11)
    code = models.CharField('کد تأیید', max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'کد یکبار مصرف'
        verbose_name_plural = 'کدهای یکبار مصرف'

    def __str__(self):
        return f'{self.mobile} - {self.code}'


class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ('manager', 'مدیر'),
        ('warehouse', 'انباردار'),
        ('accountant', 'حسابدار'),
        ('sales', 'فروشنده'),
        ('content', 'تولید محتوا'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile', verbose_name='کاربر')
    role = models.CharField('نقش', max_length=20, choices=ROLE_CHOICES)
    is_active_staff = models.BooleanField('فعال', default=True)

    class Meta:
        verbose_name = 'پروفایل کارمند'
        verbose_name_plural = 'پروفایل کارمندان'

    def __str__(self):
        return f'{self.user} - {self.get_role_display()}'
