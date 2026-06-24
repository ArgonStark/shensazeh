from django.db import models
from django_jalali.db import models as jmodels


class BlogPost(models.Model):
    title = models.CharField('عنوان', max_length=300)
    slug = models.SlugField('اسلاگ', unique=True, allow_unicode=True)
    author = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, verbose_name='نویسنده')
    content = models.TextField('محتوا')
    excerpt = models.TextField('خلاصه', max_length=500, blank=True)
    image = models.ImageField('تصویر شاخص', upload_to='blog/', blank=True)
    is_published = models.BooleanField('منتشر شده', default=False)
    views_count = models.PositiveIntegerField('تعداد بازدید', default=0)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        verbose_name = 'مقاله'
        verbose_name_plural = 'مقالات'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class BlogComment(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments', verbose_name='مقاله')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='کاربر')
    text = models.TextField('متن نظر')
    is_approved = models.BooleanField('تأیید شده', default=False)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'نظر'
        verbose_name_plural = 'نظرات'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.post.title[:30]}'


class Announcement(models.Model):
    title = models.CharField('عنوان', max_length=200)
    content = models.TextField('محتوا')
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'اطلاعیه'
        verbose_name_plural = 'اطلاعیه‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return self.title
