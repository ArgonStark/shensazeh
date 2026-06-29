from django.db import models


class SiteSetting(models.Model):
    """Singleton holding editable site-wide content (contact info, socials, about).

    Only one row ever exists; use SiteSetting.load() to fetch it.
    """
    site_name = models.CharField('نام سایت', max_length=100, default='شن‌سازه')
    tagline = models.CharField('شعار', max_length=200, blank=True,
                               default='فروشگاه تخصصی ابزار و مصالح ساختمانی')
    about_text = models.TextField('درباره ما (فوتر)', blank=True,
                                  default='فروشگاه تخصصی ابزار و مصالح ساختمانی با بیش از ده سال سابقه در ارائه بهترین محصولات و خدمات با ضمانت کیفیت.')

    # Contact
    phone = models.CharField('تلفن', max_length=30, blank=True, default='09179100761')
    email = models.EmailField('ایمیل', blank=True, default='info@shensazeh.ir')
    address = models.CharField('آدرس', max_length=300, blank=True, default='تهران، خیابان ولیعصر')
    working_hours = models.CharField('ساعت کاری', max_length=120, blank=True,
                                     default='شنبه تا پنجشنبه، ۸ تا ۱۸')
    shipping_note = models.CharField('پیام ارسال (نوار بالا)', max_length=120, blank=True,
                                     default='ارسال سریع به سراسر کشور')

    # Social links
    instagram = models.URLField('اینستاگرام', blank=True)
    telegram = models.URLField('تلگرام', blank=True)
    whatsapp = models.URLField('واتساپ', blank=True)
    linkedin = models.URLField('لینکدین', blank=True)

    copyright_text = models.CharField('متن کپی‌رایت', max_length=300, blank=True,
                                      default='تمامی حقوق مادی و معنوی این وب‌سایت متعلق به فروشگاه شن‌سازه می‌باشد.')

    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'تنظیمات سایت'
        verbose_name_plural = 'تنظیمات سایت'

    def __str__(self):
        return 'تنظیمات سایت'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
