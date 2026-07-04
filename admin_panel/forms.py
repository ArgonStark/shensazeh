from django import forms
from cheques.models import Cheque, ChequeBook, ChequePrintLayout
from finance.text import parse_jalali_date
from store.models import Category, Product, ProductReview
from inventory.models import InventoryEntry
from orders.models import Invoice, InvoiceItem
from blog.models import BlogPost, Announcement
from parties.models import Party, Payment
from services.models import Service, Project
from accounts.models import StaffProfile
from .models import SiteSetting

TW = {
    'input': 'w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition',
    'select': 'w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition bg-white',
    'textarea': 'w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition min-h-[120px]',
    'checkbox': 'w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500',
    'file': 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100',
}


class AutoSlugModelForm(forms.ModelForm):
    """Slug is optional in the panel — generated from `slug_source` (default
    'name', falls back to 'title') when left blank, kept unique per model.

    Fixes the whole-panel trap where a required SlugField rejected blank input
    even though the UI labels it 'خودکار'.
    """
    slug_source = 'name'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'slug' in self.fields:
            # Accept free text (spaces, mixed case) and slugify it in clean_slug;
            # the SlugField's own validators would otherwise reject it first.
            self.fields['slug'].required = False
            self.fields['slug'].validators = []

    def _slug_source_value(self):
        for field in (self.slug_source, 'name', 'title'):
            value = self.cleaned_data.get(field)
            if value:
                return value
        return ''

    def unique_slug(self, base):
        from django.utils.text import slugify
        slug = slugify(base, allow_unicode=True) or 'item'
        candidate, i = slug, 1
        qs = self._meta.model.objects.exclude(pk=self.instance.pk)
        while qs.filter(slug=candidate).exists():
            i += 1
            candidate = f'{slug}-{i}'
        return candidate

    def clean_slug(self):
        from django.utils.text import slugify
        slug = (self.cleaned_data.get('slug') or '').strip()
        return slugify(slug, allow_unicode=True) if slug else ''

    def clean(self):
        cleaned = super().clean()
        if 'slug' in self.fields and not cleaned.get('slug'):
            source = self._slug_source_value()
            if source:
                cleaned['slug'] = self.unique_slug(source)
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if 'slug' in self.fields and not obj.slug:
            obj.slug = self.unique_slug(getattr(obj, self.slug_source, None) or obj.title)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class ProductForm(AutoSlugModelForm):
    # The form template names this textarea "specs" and asks for one "key: value"
    # per line; we parse it into the JSONField in clean(). Declared as an
    # explicit CharField so the raw text never hits the JSONField validator.
    specs = forms.CharField(
        label='مشخصات فنی', required=False,
        widget=forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3,
                                     'placeholder': 'هر مشخصه در یک خط، مثل:\nرنگ: سفید\nوزن: ۲ کیلوگرم'}),
    )
    expiry_date = forms.CharField(
        label='تاریخ انقضا', required=False,
        widget=forms.TextInput(attrs={'class': TW['input'], 'placeholder': '1405/06/01 (اختیاری)', 'dir': 'ltr'}),
    )

    class Meta:
        model = Product
        fields = ['name', 'slug', 'code', 'category', 'description', 'unit',
                  'price', 'purchase_price', 'barcode', 'stock', 'reorder_point', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'نام محصول'}),
            'slug': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'اسلاگ (خودکار)'}),
            'code': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'خالی = خودکار', 'dir': 'ltr'}),
            'category': forms.Select(attrs={'class': TW['select']}),
            'description': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4}),
            'unit': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'عدد / کیلوگرم / متر'}),
            'price': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'قیمت فروش (ریال)'}),
            'purchase_price': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'قیمت خرید (ریال)'}),
            'barcode': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'بارکد'}),
            'stock': forms.NumberInput(attrs={'class': TW['input']}),
            'reorder_point': forms.NumberInput(attrs={'class': TW['input']}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].empty_label = 'یک دسته‌بندی انتخاب کنید'
        if self.instance.pk:
            # Stock is set once at creation; afterwards it only moves through
            # inventory movements (disabled fields ignore posted values).
            self.fields['stock'].disabled = True
            if self.instance.specifications:
                self.fields['specs'].initial = '\n'.join(
                    f'{k}: {v}' for k, v in self.instance.specifications.items())
            if self.instance.expiry_date:
                self.fields['expiry_date'].initial = self.instance.expiry_date.strftime('%Y/%m/%d')

    def clean_specs(self):
        """Parse 'key: value' lines into a dict for the JSONField."""
        text = (self.cleaned_data.get('specs') or '').strip()
        specs = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if ':' in line:
                key, value = line.split(':', 1)
                specs[key.strip()] = value.strip()
            else:
                specs[line] = ''
        return specs

    def clean_expiry_date(self):
        raw = (self.cleaned_data.get('expiry_date') or '').strip()
        if not raw:
            return None
        parsed = parse_jalali_date(raw)
        if parsed is None:
            raise forms.ValidationError('تاریخ را به شکل ۱۴۰۵/۰۶/۰۱ وارد کنید یا خالی بگذارید.')
        return parsed

    def save(self, commit=True):
        product = super().save(commit=False)
        product.specifications = self.cleaned_data.get('specs') or {}
        product.expiry_date = self.cleaned_data.get('expiry_date')
        if commit:
            product.save()
        return product


class CategoryForm(AutoSlugModelForm):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'parent', 'image', 'description', 'order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TW['input']}),
            'slug': forms.TextInput(attrs={'class': TW['input']}),
            'parent': forms.Select(attrs={'class': TW['select']}),
            'image': forms.ClearableFileInput(attrs={'class': TW['file']}),
            'description': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3}),
            'order': forms.NumberInput(attrs={'class': TW['input']}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class InventoryEntryForm(forms.ModelForm):
    class Meta:
        model = InventoryEntry
        fields = ['product', 'entry_type', 'quantity', 'unit_cost', 'supplier', 'reference', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': TW['select']}),
            'entry_type': forms.RadioSelect(attrs={'class': 'sr-only peer'}),
            'quantity': forms.NumberInput(attrs={'class': TW['input'], 'min': 1}),
            'unit_cost': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'قیمت واحد به ریال (اختیاری)'}),
            'supplier': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'نام تأمین‌کننده'}),
            'reference': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'شماره مرجع'}),
            'notes': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_cost'].required = False
        # The manual entry form only offers plain in/out; returns and
        # adjustments are recorded by their source documents.
        self.fields['entry_type'].choices = [
            ('in', 'ورود کالا'),
            ('out', 'خروج کالا'),
        ]


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['customer_name', 'customer_mobile', 'customer_address', 'discount', 'tax', 'notes', 'is_paid']
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'نام مشتری'}),
            'customer_mobile': forms.TextInput(attrs={'class': TW['input'], 'placeholder': '09xxxxxxxxx'}),
            'customer_address': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
            'discount': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': '0'}),
            'tax': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': '0'}),
            'notes': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
            'is_paid': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class BlogPostForm(AutoSlugModelForm):
    slug_source = 'title'

    class Meta:
        model = BlogPost
        fields = ['title', 'slug', 'content', 'excerpt', 'image', 'is_published']
        widgets = {
            'title': forms.TextInput(attrs={'class': TW['input']}),
            'slug': forms.TextInput(attrs={'class': TW['input']}),
            'content': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 15}),
            'excerpt': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3}),
            'image': forms.ClearableFileInput(attrs={'class': TW['file']}),
            'is_published': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': TW['input']}),
            'content': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class ServiceForm(AutoSlugModelForm):
    slug_source = 'title'

    class Meta:
        model = Service
        fields = ['title', 'slug', 'description', 'icon', 'image', 'is_active', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': TW['input']}),
            'slug': forms.TextInput(attrs={'class': TW['input']}),
            'description': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4}),
            'icon': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'CSS class آیکون'}),
            'image': forms.ClearableFileInput(attrs={'class': TW['file']}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
            'order': forms.NumberInput(attrs={'class': TW['input']}),
        }


class ProjectForm(AutoSlugModelForm):
    slug_source = 'title'

    class Meta:
        model = Project
        fields = ['title', 'slug', 'description', 'client', 'location', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': TW['input']}),
            'slug': forms.TextInput(attrs={'class': TW['input']}),
            'description': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4}),
            'client': forms.TextInput(attrs={'class': TW['input']}),
            'location': forms.TextInput(attrs={'class': TW['input']}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class SiteSettingForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = [
            'site_name', 'tagline', 'about_text',
            'phone', 'email', 'address', 'working_hours', 'shipping_note',
            'instagram', 'telegram', 'whatsapp', 'linkedin', 'copyright_text',
            'vat_rate', 'legal_name', 'economic_code', 'national_id',
            'registration_number', 'postal_code',
            'invoice_sms_enabled', 'invoice_sms_template',
        ]
        widgets = {
            'site_name': forms.TextInput(attrs={'class': TW['input']}),
            'tagline': forms.TextInput(attrs={'class': TW['input']}),
            'about_text': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'email': forms.EmailInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'address': forms.TextInput(attrs={'class': TW['input']}),
            'working_hours': forms.TextInput(attrs={'class': TW['input']}),
            'shipping_note': forms.TextInput(attrs={'class': TW['input']}),
            'instagram': forms.URLInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': 'https://instagram.com/...'}),
            'telegram': forms.URLInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': 'https://t.me/...'}),
            'whatsapp': forms.URLInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': 'https://wa.me/...'}),
            'linkedin': forms.URLInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': 'https://linkedin.com/...'}),
            'copyright_text': forms.TextInput(attrs={'class': TW['input']}),
            'vat_rate': forms.NumberInput(attrs={'class': TW['input'], 'min': 0, 'max': 100}),
            'legal_name': forms.TextInput(attrs={'class': TW['input']}),
            'economic_code': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'national_id': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'registration_number': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'postal_code': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'invoice_sms_enabled': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
            'invoice_sms_template': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
        }


class PartyForm(forms.ModelForm):
    class Meta:
        model = Party
        fields = [
            'party_type', 'name', 'company', 'mobile', 'phone',
            'national_id', 'economic_code', 'province', 'city', 'address',
            'postal_code', 'user', 'tags', 'notes', 'is_active',
        ]
        widgets = {
            'party_type': forms.Select(attrs={'class': TW['select']}),
            'name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'نام شخص یا شرکت'}),
            'company': forms.TextInput(attrs={'class': TW['input']}),
            'mobile': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': '09xxxxxxxxx'}),
            'phone': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'national_id': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'economic_code': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'province': forms.TextInput(attrs={'class': TW['input']}),
            'city': forms.TextInput(attrs={'class': TW['input']}),
            'address': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
            'postal_code': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'user': forms.Select(attrs={'class': TW['select']}),
            'tags': forms.SelectMultiple(attrs={'class': TW['select'], 'size': 4}),
            'notes': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['kind', 'method', 'amount', 'reference', 'description']
        widgets = {
            'kind': forms.Select(attrs={'class': TW['select']}),
            'method': forms.Select(attrs={'class': TW['select']}),
            'amount': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'مبلغ به ریال', 'min': 1}),
            'reference': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': 'شماره پیگیری (اختیاری)'}),
            'description': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'شرح (اختیاری)'}),
        }


class ChequeForm(forms.ModelForm):
    due_date = forms.CharField(
        label='تاریخ سررسید (شمسی)',
        widget=forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': '1404/06/15'}),
    )

    class Meta:
        model = Cheque
        fields = ['direction', 'party', 'invoice', 'cheque_book', 'serial', 'sayad_id',
                  'bank_name', 'branch', 'amount', 'due_date', 'payee', 'description']
        widgets = {
            'direction': forms.Select(attrs={'class': TW['select']}),
            'party': forms.Select(attrs={'class': TW['select']}),
            'invoice': forms.Select(attrs={'class': TW['select']}),
            'cheque_book': forms.Select(attrs={'class': TW['select']}),
            'serial': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'sayad_id': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': '۱۶ رقم (اختیاری)'}),
            'bank_name': forms.TextInput(attrs={'class': TW['input']}),
            'branch': forms.TextInput(attrs={'class': TW['input']}),
            'amount': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'مبلغ به ریال', 'min': 1}),
            'payee': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'در وجه (برای چاپ)'}),
            'description': forms.TextInput(attrs={'class': TW['input']}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from parties.models import Party
        from orders.models import Invoice
        self.fields['party'].queryset = Party.objects.filter(is_active=True).order_by('name')
        self.fields['invoice'].queryset = Invoice.objects.filter(status='issued').order_by('-created_at')
        self.fields['invoice'].required = False
        self.fields['cheque_book'].queryset = ChequeBook.objects.filter(is_active=True)
        self.fields['cheque_book'].required = False
        if self.instance.pk and self.instance.due_date:
            self.initial.setdefault('due_date', self.instance.due_date.strftime('%Y/%m/%d'))

    def clean_due_date(self):
        parsed = parse_jalali_date(self.cleaned_data['due_date'])
        if parsed is None:
            raise forms.ValidationError('تاریخ را به شکل ۱۴۰۴/۰۶/۱۵ وارد کنید.')
        return parsed

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('مبلغ باید بزرگ‌تر از صفر باشد.')
        return amount


class ChequeBookForm(forms.ModelForm):
    class Meta:
        model = ChequeBook
        fields = ['bank_name', 'branch', 'account_number', 'serial_from', 'serial_to', 'notes', 'is_active']
        widgets = {
            'bank_name': forms.TextInput(attrs={'class': TW['input']}),
            'branch': forms.TextInput(attrs={'class': TW['input']}),
            'account_number': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'serial_from': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'serial_to': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
            'notes': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }


class ChequePrintLayoutForm(forms.ModelForm):
    class Meta:
        model = ChequePrintLayout
        fields = ['bank_name', 'paper_width', 'paper_height', 'date_x', 'date_y',
                  'amount_x', 'amount_y', 'words_x', 'words_y', 'payee_x', 'payee_y']
        widgets = {field: forms.NumberInput(attrs={'class': TW['input']})
                   for field in ['paper_width', 'paper_height', 'date_x', 'date_y',
                                 'amount_x', 'amount_y', 'words_x', 'words_y', 'payee_x', 'payee_y']}
        widgets['bank_name'] = forms.TextInput(attrs={'class': TW['input']})


class CashTransactionForm(forms.ModelForm):
    date = forms.CharField(
        label='تاریخ (شمسی)',
        widget=forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr', 'placeholder': '1404/04/13'}),
    )

    class Meta:
        from finance.models import CashTransaction
        model = CashTransaction
        fields = ['kind', 'category', 'amount', 'date', 'description', 'reference']
        widgets = {
            'kind': forms.Select(attrs={'class': TW['select']}),
            'category': forms.Select(attrs={'class': TW['select']}),
            'amount': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'مبلغ به ریال', 'min': 1}),
            'description': forms.TextInput(attrs={'class': TW['input']}),
            'reference': forms.TextInput(attrs={'class': TW['input'], 'dir': 'ltr'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        import jdatetime
        from finance.models import ExpenseCategory
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_active=True)
        self.initial.setdefault('date', jdatetime.date.today().strftime('%Y/%m/%d'))

    def clean_date(self):
        parsed = parse_jalali_date(self.cleaned_data['date'])
        if parsed is None:
            raise forms.ValidationError('تاریخ را به شکل ۱۴۰۴/۰۴/۱۳ وارد کنید.')
        return parsed

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        kind = cleaned.get('kind')
        if category and kind and category.kind != kind:
            raise forms.ValidationError('دسته انتخاب‌شده با نوع تراکنش هم‌خوان نیست.')
        return cleaned


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        from finance.models import ExpenseCategory
        model = ExpenseCategory
        fields = ['name', 'kind']
        widgets = {
            'name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'مثلاً کرایه حمل'}),
            'kind': forms.Select(attrs={'class': TW['select']}),
        }


class CampaignForm(forms.ModelForm):
    class Meta:
        from crm.models import Campaign
        model = Campaign
        fields = ['name', 'message', 'party_type', 'tag']
        widgets = {
            'name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'مثلاً تخفیف پایان فصل'}),
            'message': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4,
                                             'placeholder': '{name} عزیز، ...'}),
            'party_type': forms.Select(attrs={'class': TW['select']}),
            'tag': forms.Select(attrs={'class': TW['select']}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from parties.models import Party
        self.fields['party_type'].widget.choices = [('', 'همه طرف حساب‌ها')] + list(Party.TYPE_CHOICES)
        self.fields['party_type'].required = False
        self.fields['tag'].required = False


class StaffForm(forms.Form):
    mobile = forms.CharField(
        max_length=11,
        widget=forms.TextInput(attrs={'class': TW['input'], 'placeholder': '09xxxxxxxxx'}),
        label='شماره موبایل',
    )
    role = forms.ChoiceField(
        choices=StaffProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': TW['select']}),
        label='نقش',
    )
