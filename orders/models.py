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


class NumberSeries(models.Model):
    """Configurable sequential numbering per document type.

    Allocation happens inside the issue transaction with the row locked
    (orders.services.allocate_number) so numbers are gapless per issue attempt
    and never duplicated under concurrency.
    """
    doc_type = models.CharField('نوع سند', max_length=20, unique=True)
    prefix = models.CharField('پیشوند', max_length=10, blank=True)
    next_number = models.PositiveIntegerField('شماره بعدی', default=1)
    padding = models.PositiveSmallIntegerField('طول عدد', default=5)

    class Meta:
        verbose_name = 'سری شماره‌گذاری'
        verbose_name_plural = 'سری‌های شماره‌گذاری'

    def __str__(self):
        return f'{self.doc_type}: {self.prefix}{self.next_number}'


class Invoice(models.Model):
    """A financial document. One model, five types (فاکتور فروش/خرید/برگشتی‌ها/پیش‌فاکتور).

    Lifecycle: draft → issued → cancelled. Issue and cancel run through
    orders.services (atomic stock + party-ledger side effects); issued
    documents are never edited or hard-deleted.
    """
    DOC_TYPE_CHOICES = [
        ('sale', 'فاکتور فروش'),
        ('purchase', 'فاکتور خرید'),
        ('sale_return', 'برگشت از فروش'),
        ('purchase_return', 'برگشت از خرید'),
        ('proforma', 'پیش‌فاکتور'),
    ]
    STATUS_CHOICES = [
        ('draft', 'پیش‌نویس'),
        ('issued', 'صادر شده'),
        ('cancelled', 'باطل شده'),
    ]
    SETTLEMENT_CHOICES = [
        ('cash', 'نقدی (تسویه کامل)'),
        ('partial', 'پرداخت جزئی'),
        ('credit', 'نسیه'),
        ('cheque', 'چک'),
        ('card', 'کارت به کارت'),
        ('installment', 'اقساطی'),
    ]
    invoice_number = models.CharField('شماره فاکتور', max_length=20, unique=True)
    doc_type = models.CharField('نوع سند', max_length=20, choices=DOC_TYPE_CHOICES, default='sale')
    status = models.CharField('وضعیت', max_length=10, choices=STATUS_CHOICES, default='draft')
    party = models.ForeignKey('parties.Party', on_delete=models.PROTECT, null=True, blank=True,
                              related_name='invoices', verbose_name='طرف حساب')
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='invoice', verbose_name='سفارش مرتبط')
    # Snapshot of the party at issue time (what gets printed stays immutable)
    customer_name = models.CharField('نام مشتری', max_length=200)
    customer_mobile = models.CharField('موبایل مشتری', max_length=11, blank=True)
    customer_address = models.TextField('آدرس مشتری', blank=True)
    company_logo = models.ImageField('لوگوی شرکت', upload_to='invoices/logos/', blank=True)
    # Totals — computed server-side by orders.services.recompute_totals
    subtotal = models.PositiveBigIntegerField('جمع اقلام (ریال)', default=0)
    items_discount = models.PositiveBigIntegerField('تخفیف سطری (ریال)', default=0)
    discount = models.PositiveBigIntegerField('تخفیف کلی (ریال)', default=0)
    vat_rate = models.PositiveSmallIntegerField('نرخ مالیات (٪)', default=0)
    tax = models.PositiveBigIntegerField('مالیات (ریال)', default=0)
    total = models.PositiveBigIntegerField('جمع کل (ریال)', default=0)
    # Settlement at issue
    settlement_type = models.CharField('نحوه تسویه', max_length=12, choices=SETTLEMENT_CHOICES, default='cash')
    paid_amount = models.PositiveBigIntegerField('مبلغ پرداختی (ریال)', default=0)
    due_date = jmodels.jDateField('سررسید مانده', null=True, blank=True)
    is_paid = models.BooleanField('تسویه شده', default=False)
    notes = models.TextField('توضیحات', blank=True)
    # Idempotency guard against double-submit (unique per form render)
    submission_token = models.UUIDField('توکن ثبت', null=True, blank=True, unique=True, editable=False)
    issued_at = jmodels.jDateTimeField('تاریخ صدور', null=True, blank=True)
    issued_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='issued_invoices', verbose_name='صادرکننده')
    cancelled_at = jmodels.jDateTimeField('تاریخ ابطال', null=True, blank=True)
    cancelled_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='cancelled_invoices', verbose_name='باطل‌کننده')
    created_at = jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = jmodels.jDateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        verbose_name = 'فاکتور'
        verbose_name_plural = 'فاکتورها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_doc_type_display()} {self.invoice_number}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Drafts get a temporary number; the real series number is
            # allocated at issue time by the service.
            self.invoice_number = f'DRAFT-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    @property
    def is_editable(self) -> bool:
        return self.status == 'draft'

    @property
    def remaining_amount(self) -> int:
        return max(0, self.total - self.paid_amount)


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', verbose_name='فاکتور')
    product = models.ForeignKey('store.Product', on_delete=models.PROTECT, null=True, blank=True,
                                verbose_name='محصول')  # null → free-text service line
    description = models.CharField('شرح', max_length=300, blank=True)
    unit = models.CharField('واحد', max_length=20, blank=True)
    quantity = models.PositiveIntegerField('تعداد')
    unit_price = models.PositiveBigIntegerField('قیمت واحد (ریال)')
    discount = models.PositiveBigIntegerField('تخفیف سطر (ریال)', default=0)
    vat_rate = models.PositiveSmallIntegerField('نرخ مالیات سطر (٪)', null=True, blank=True,
                                                help_text='خالی = نرخ فاکتور')

    class Meta:
        verbose_name = 'آیتم فاکتور'
        verbose_name_plural = 'آیتم‌های فاکتور'

    @property
    def gross(self) -> int:
        return self.unit_price * self.quantity

    @property
    def net(self) -> int:
        return self.gross - self.discount

    # Kept for existing templates
    @property
    def total_price(self) -> int:
        return self.gross

    @property
    def label(self) -> str:
        return self.description or (self.product.name if self.product else '')

    def __str__(self):
        return f'{self.label} x {self.quantity}'
