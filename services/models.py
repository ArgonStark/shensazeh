from django.db import models
from django.urls import reverse
from django_jalali.db import models as jmodels


class Service(models.Model):
    title = models.CharField('عنوان خدمت', max_length=200)
    slug = models.SlugField('اسلاگ', unique=True, allow_unicode=True)
    description = models.TextField('توضیحات')
    icon = models.CharField('آیکون (CSS class)', max_length=50, blank=True)
    # SEO — blank falls back to the natural title/description at render time
    meta_title = models.CharField('عنوان سئو', max_length=70, blank=True,
                                  help_text='خالی بماند تا از عنوان اصلی استفاده شود. حداکثر ۷۰ کاراکتر.')
    meta_description = models.CharField('توضیحات سئو', max_length=160, blank=True,
                                        help_text='توضیح کوتاه برای نتایج گوگل. حداکثر ۱۶۰ کاراکتر.')
    image = models.ImageField('تصویر', upload_to='services/', blank=True)
    is_active = models.BooleanField('فعال', default=True)
    order = models.PositiveIntegerField('ترتیب', default=0)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'خدمت'
        verbose_name_plural = 'خدمات'
        ordering = ['order']

    def get_absolute_url(self):
        return reverse('services:service_detail', args=[self.slug])

    def __str__(self):
        return self.title


class Project(models.Model):
    title = models.CharField('عنوان پروژه', max_length=200)
    slug = models.SlugField('اسلاگ', unique=True, allow_unicode=True)
    description = models.TextField('توضیحات')
    client = models.CharField('کارفرما', max_length=200, blank=True)
    location = models.CharField('مکان', max_length=200, blank=True)
    # SEO — blank falls back to the natural title/description at render time
    meta_title = models.CharField('عنوان سئو', max_length=70, blank=True,
                                  help_text='خالی بماند تا از عنوان اصلی استفاده شود. حداکثر ۷۰ کاراکتر.')
    meta_description = models.CharField('توضیحات سئو', max_length=160, blank=True,
                                        help_text='توضیح کوتاه برای نتایج گوگل. حداکثر ۱۶۰ کاراکتر.')
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'پروژه'
        verbose_name_plural = 'پروژه‌ها'
        ordering = ['-created_at']

    def get_absolute_url(self):
        return reverse('services:project_detail', args=[self.slug])

    def __str__(self):
        return self.title


class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='images', verbose_name='پروژه')
    image = models.ImageField('تصویر', upload_to='projects/')
    caption = models.CharField('توضیح', max_length=200, blank=True)
    order = models.PositiveIntegerField('ترتیب', default=0)

    class Meta:
        verbose_name = 'تصویر پروژه'
        verbose_name_plural = 'تصاویر پروژه'
        ordering = ['order']
