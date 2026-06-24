import uuid
from django.db import models
from django_jalali.db import models as jmodels


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'در انتظار'),
        ('confirmed', 'تأیید شده'),
        ('processing', 'در حال پردازش'),
        ('shipped', 'ارسال شده'),
        ('delivered', 'تحویل داده شده'),
        ('cancelled', 'لغو شده'),
    ]
    order_number = models.CharField('شماره سفارش', max_length=20, unique=True, editable=False)
    customer = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='orders', verbose_name='مشتری')
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.PositiveBigIntegerField('مبلغ کل', default=0)
    discount = models.PositiveBigIntegerField('تخفیف (ریال)', default=0)
    tax = models.PositiveBigIntegerField('مالیات (ریال)', default=0)
    notes = models.TextField('یادداشت', blank=True)
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'سفارش'
        verbose_name_plural = 'سفارشات'
        ordering = ['-created_at']

    def __str__(self):
        return f'سفارش {self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    @property
    def final_amount(self):
        return self.total_amount - self.discount + self.tax

    def recalculate_total(self):
        self.total_amount = sum(item.total_price for item in self.items.all())
        self.save(update_fields=['total_amount'])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='سفارش')
    product = models.ForeignKey('store.Product', on_delete=models.PROTECT, verbose_name='محصول')
    quantity = models.PositiveIntegerField('تعداد')
    unit_price = models.PositiveBigIntegerField('قیمت واحد')

    class Meta:
        verbose_name = 'آیتم سفارش'
        verbose_name_plural = 'آیتم‌های سفارش'

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    @property
    def total_price(self):
        return self.unit_price * self.quantity


class Invoice(models.Model):
    invoice_number = models.CharField('شماره فاکتور', max_length=20, unique=True, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='invoice', verbose_name='سفارش')
    customer_name = models.CharField('نام مشتری', max_length=200)
    customer_mobile = models.CharField('موبایل مشتری', max_length=11, blank=True)
    customer_address = models.TextField('آدرس مشتری', blank=True)
    company_logo = models.ImageField('لوگوی شرکت', upload_to='invoices/logos/', blank=True)
    subtotal = models.PositiveBigIntegerField('جمع فرعی', default=0)
    discount = models.PositiveBigIntegerField('تخفیف', default=0)
    tax = models.PositiveBigIntegerField('مالیات', default=0)
    total = models.PositiveBigIntegerField('جمع کل', default=0)
    notes = models.TextField('توضیحات', blank=True)
    is_paid = models.BooleanField('پرداخت شده', default=False)
    created_at = jmodels.jDateTimeField('تاریخ صدور', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        verbose_name = 'فاکتور'
        verbose_name_plural = 'فاکتورها'
        ordering = ['-created_at']

    def __str__(self):
        return f'فاکتور {self.invoice_number}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f'INV-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', verbose_name='فاکتور')
    product = models.ForeignKey('store.Product', on_delete=models.PROTECT, verbose_name='محصول')
    description = models.CharField('شرح', max_length=300, blank=True)
    quantity = models.PositiveIntegerField('تعداد')
    unit_price = models.PositiveBigIntegerField('قیمت واحد')

    class Meta:
        verbose_name = 'آیتم فاکتور'
        verbose_name_plural = 'آیتم‌های فاکتور'

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f'{self.description or self.product.name} x {self.quantity}'
