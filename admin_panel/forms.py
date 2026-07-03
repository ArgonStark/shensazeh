from django import forms
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


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'slug', 'code', 'category', 'description', 'specifications', 'unit',
                  'price', 'purchase_price', 'barcode', 'stock', 'reorder_point', 'expiry_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'نام محصول'}),
            'slug': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'اسلاگ (خودکار)'}),
            'code': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'خالی = خودکار', 'dir': 'ltr'}),
            'category': forms.Select(attrs={'class': TW['select']}),
            'description': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 4}),
            'specifications': forms.Textarea(attrs={'class': TW['textarea'], 'rows': 3, 'placeholder': '{"رنگ": "سفید", "وزن": "1kg"}'}),
            'unit': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'عدد / کیلوگرم / متر'}),
            'price': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'قیمت فروش (ریال)'}),
            'purchase_price': forms.NumberInput(attrs={'class': TW['input'], 'placeholder': 'قیمت خرید (ریال)'}),
            'barcode': forms.TextInput(attrs={'class': TW['input'], 'placeholder': 'بارکد'}),
            'stock': forms.NumberInput(attrs={'class': TW['input']}),
            'reorder_point': forms.NumberInput(attrs={'class': TW['input']}),
            'expiry_date': forms.TextInput(attrs={'class': TW['input'], 'placeholder': '1405/06/01 (اختیاری)', 'dir': 'ltr'}),
            'is_active': forms.CheckboxInput(attrs={'class': TW['checkbox']}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Stock is set once at creation; afterwards it only moves through
            # inventory movements (disabled fields ignore posted values).
            self.fields['stock'].disabled = True


class CategoryForm(forms.ModelForm):
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


class BlogPostForm(forms.ModelForm):
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


class ServiceForm(forms.ModelForm):
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


class ProjectForm(forms.ModelForm):
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
