from django.db import models
from django_jalali.db import models as jmodels


class Category(models.Model):
    name = models.CharField('نام دسته‌بندی', max_length=100)
    slug = models.SlugField('اسلاگ', unique=True, allow_unicode=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                               related_name='children', verbose_name='دسته‌بندی والد')
    image = models.ImageField('تصویر', upload_to='categories/', blank=True)
    description = models.TextField('توضیحات', blank=True)
    order = models.PositiveIntegerField('ترتیب', default=0)
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'
        ordering = ['order', 'name']

    def __str__(self):
        if self.parent:
            return f'{self.parent} → {self.name}'
        return self.name


class Product(models.Model):
    name = models.CharField('نام محصول', max_length=200)
    slug = models.SlugField('اسلاگ', unique=True, allow_unicode=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products', verbose_name='دسته‌بندی')
    description = models.TextField('توضیحات', blank=True)
    specifications = models.JSONField('مشخصات فنی', default=dict, blank=True)
    price = models.PositiveBigIntegerField('قیمت (ریال)')
    barcode = models.CharField('بارکد', max_length=50, blank=True, unique=True, null=True)
    stock = models.PositiveIntegerField('موجودی', default=0)
    is_active = models.BooleanField('فعال', default=True)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'محصول'
        verbose_name_plural = 'محصولات'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()

    @property
    def image_url(self):
        """URL of the primary image, or None — convenient for templates."""
        img = self.primary_image
        return img.image.url if img else None

    @property
    def is_available(self):
        """In stock and active."""
        return self.is_active and self.stock > 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images', verbose_name='محصول')
    image = models.ImageField('تصویر', upload_to='products/')
    alt_text = models.CharField('متن جایگزین', max_length=200, blank=True)
    is_primary = models.BooleanField('تصویر اصلی', default=False)
    order = models.PositiveIntegerField('ترتیب', default=0)

    class Meta:
        verbose_name = 'تصویر محصول'
        verbose_name_plural = 'تصاویر محصولات'
        ordering = ['order']

    def __str__(self):
        return f'{self.product.name} - تصویر {self.order}'


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews', verbose_name='محصول')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, verbose_name='کاربر')
    rating = models.PositiveSmallIntegerField('امتیاز', choices=[(i, i) for i in range(1, 6)])
    text = models.TextField('متن نظر')
    is_approved = models.BooleanField('تأیید شده', default=False)
    created_at = jmodels.jDateTimeField('تاریخ', auto_now_add=True)

    class Meta:
        verbose_name = 'نظر محصول'
        verbose_name_plural = 'نظرات محصولات'
        unique_together = ['product', 'user']

    def __str__(self):
        return f'{self.user} - {self.product}'
