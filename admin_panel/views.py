import json
import uuid

import anthropic
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView

from accounts.models import User, StaffProfile
from blog.models import BlogPost, BlogComment, Announcement
from dashboard.models import SiteVisit
from finance.audit import log_action, model_snapshot
from finance.models import AuditLog
from inventory.models import InventoryEntry
from inventory.services import StockError, record_movement
from orders.models import Order, OrderItem, Invoice, InvoiceItem
from orders.services import InvoiceError, cancel_invoice, issue_invoice, recompute_totals
from services.models import Service, Project, ProjectImage
from store.models import Category, Product, ProductImage, ProductReview

from cheques.models import Cheque, ChequeBook, ChequePrintLayout
from cheques.services import ChequeError, set_cheque_status
from parties.models import LedgerEntry, Party, PartyTag, Payment
from parties.services import LedgerError, ledger_rows_with_balance, record_payment

from . import permissions as panel_permissions
from .forms import (
    ProductForm, CategoryForm, InventoryEntryForm,
    BlogPostForm, AnnouncementForm, PartyForm, PaymentForm,
    CashTransactionForm, ExpenseCategoryForm,
    ChequeForm, ChequeBookForm, ChequePrintLayoutForm,
    ServiceForm, ProjectForm, StaffForm,
)


class StaffRequiredMixin(UserPassesTestMixin):
    login_url = '/accounts/login/'

    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class PanelPermissionMixin(StaffRequiredMixin):
    """Staff gate + a required Django permission, checked server-side per view.

    Authenticated staff without the permission get a 403 (handled by
    UserPassesTestMixin); anonymous users are redirected to login.
    """
    permission_required = None

    def test_func(self):
        if not super().test_func():
            return False
        if not self.permission_required:
            return True
        required = ([self.permission_required]
                    if isinstance(self.permission_required, str) else self.permission_required)
        return self.request.user.has_perms(required)


# ─── Dashboard ───────────────────────────────────────────────

class AdminDashboardView(StaffRequiredMixin, TemplateView):
    template_name = 'admin_panel/dashboard.html'

    def get_context_data(self, **kwargs):
        import datetime

        import jdatetime
        ctx = super().get_context_data(**kwargs)
        issued_sales = Invoice.objects.filter(doc_type='sale', status='issued')
        ctx['total_sales'] = issued_sales.aggregate(t=Sum('total'))['t'] or 0
        ctx['order_count'] = Order.objects.exclude(status='cancelled').count()
        ctx['total_products'] = Product.objects.filter(is_active=True).count()
        ctx['user_count'] = User.objects.count()
        ctx['out_of_stock'] = Product.objects.filter(is_active=True, stock=0).count()
        ctx['low_stock_products'] = Product.objects.filter(
            is_active=True, stock__gt=0, stock__lte=F('reorder_point')).order_by('stock')[:10]
        ctx['recent_invoices'] = Invoice.objects.select_related('party').order_by('-created_at')[:5]
        ctx['invoice_count'] = Invoice.objects.count()
        ctx['unpaid_sales_count'] = issued_sales.filter(is_paid=False).count()
        ctx['unpaid_sales_total'] = sum(inv.remaining_amount for inv in issued_sales.filter(is_paid=False))
        ctx['announcements'] = Announcement.objects.filter(is_active=True)[:5]

        # Receivable / payable across all party ledgers
        balances = (LedgerEntry.objects.values('party')
                    .annotate(debit=Sum('amount', filter=Q(entry_type=LedgerEntry.DEBIT), default=0),
                              credit=Sum('amount', filter=Q(entry_type=LedgerEntry.CREDIT), default=0)))
        receivable = payable = 0
        for row in balances:
            net = row['debit'] - row['credit']
            if net > 0:
                receivable += net
            else:
                payable -= net
        ctx['total_receivable'] = receivable
        ctx['total_payable'] = payable

        # Cheques nearing due (7 days) + overdue
        today = jdatetime.date.today()
        pending_cheques = Cheque.objects.filter(status='pending').select_related('party')
        ctx['cheques_due_soon'] = pending_cheques.filter(
            due_date__gte=today, due_date__lte=today + datetime.timedelta(days=7))[:8]
        ctx['overdue_cheques_count'] = pending_cheques.filter(due_date__lt=today).count()

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        ctx['total_visits'] = SiteVisit.objects.count()
        ctx['today_visits'] = SiteVisit.objects.filter(visited_at__gte=today_start).count()

        ctx['category_product_counts'] = (
            Category.objects.filter(is_active=True)
            .annotate(product_count=Count('products'))
            .values('name', 'product_count')
            .order_by('-product_count')[:8]
        )

        # Sales chart: last 30 days of issued sale documents (Toman)
        from datetime import timedelta
        sales_labels, sales_values = [], []
        for i in range(29, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            total = (issued_sales.filter(issued_at__gte=day_start, issued_at__lt=day_end)
                     .aggregate(t=Sum('total'))['t'] or 0)
            jd = jdatetime.datetime.fromgregorian(datetime=day)
            sales_labels.append(f'{jd.month}/{jd.day}')
            sales_values.append(int(total) // 10)
        ctx['sales_labels'] = json.dumps(sales_labels)
        ctx['sales_values'] = json.dumps(sales_values)

        cat_labels = [c['name'] for c in ctx['category_product_counts']]
        cat_values = [c['product_count'] for c in ctx['category_product_counts']]
        ctx['cat_labels'] = json.dumps(cat_labels, ensure_ascii=False)
        ctx['cat_values'] = json.dumps(cat_values)
        return ctx


# ─── Products ────────────────────────────────────────────────

class AdminProductListView(PanelPermissionMixin, ListView):
    permission_required = 'store.view_product'
    template_name = 'admin_panel/store/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        cat = self.request.GET.get('category', '').strip()
        stock = self.request.GET.get('stock', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(barcode__icontains=q))
        if cat:
            qs = qs.filter(category_id=cat)
        if stock == 'in_stock':
            qs = qs.filter(stock__gt=F('reorder_point'))
        elif stock == 'out_of_stock':
            qs = qs.filter(stock=0)
        elif stock == 'low_stock':
            qs = qs.filter(stock__gt=0, stock__lte=F('reorder_point'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Category.objects.filter(is_active=True)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_stock'] = self.request.GET.get('stock', '')
        return ctx


class AdminProductCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'store.add_product'
    template_name = 'admin_panel/store/product_form.html'
    form_class = ProductForm
    success_url = reverse_lazy('admin_panel:product_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        images = self.request.FILES.getlist('images')
        for i, img in enumerate(images[:5]):
            ProductImage.objects.create(product=self.object, image=img, order=i, is_primary=(i == 0))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'افزودن محصول'
        return ctx


class AdminProductEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'store.change_product'
    model = Product
    template_name = 'admin_panel/store/product_form.html'
    form_class = ProductForm
    success_url = reverse_lazy('admin_panel:product_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        images = self.request.FILES.getlist('images')
        for i, img in enumerate(images[:5]):
            ProductImage.objects.create(product=self.object, image=img, order=i)
        delete_ids = self.request.POST.getlist('delete_image')
        if delete_ids:
            ProductImage.objects.filter(id__in=delete_ids, product=self.object).delete()
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'ویرایش محصول'
        ctx['existing_images'] = self.object.images.all()
        return ctx


class AdminProductDeleteView(PanelPermissionMixin, DeleteView):
    permission_required = 'store.delete_product'
    model = Product
    success_url = reverse_lazy('admin_panel:product_list')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


# ─── Categories ──────────────────────────────────────────────

class AdminCategoryListView(PanelPermissionMixin, ListView):
    permission_required = 'store.view_category'
    template_name = 'admin_panel/store/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.filter(parent__isnull=True).prefetch_related('children').annotate(product_count=Count('products'))


class AdminCategoryCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'store.add_category'
    model = Category
    form_class = CategoryForm
    template_name = 'admin_panel/store/category_form.html'
    success_url = reverse_lazy('admin_panel:category_list')


class AdminCategoryEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'store.change_category'
    model = Category
    form_class = CategoryForm
    template_name = 'admin_panel/store/category_form.html'
    success_url = reverse_lazy('admin_panel:category_list')


class AdminCategoryDeleteView(PanelPermissionMixin, DeleteView):
    permission_required = 'store.delete_category'
    model = Category
    success_url = reverse_lazy('admin_panel:category_list')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


# ─── Reviews ─────────────────────────────────────────────────

class AdminReviewListView(PanelPermissionMixin, ListView):
    permission_required = 'store.view_productreview'
    template_name = 'admin_panel/store/review_list.html'
    context_object_name = 'reviews'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductReview.objects.select_related('product', 'user').order_by('-created_at')
        status = self.request.GET.get('status', '')
        if status == 'approved':
            qs = qs.filter(is_approved=True)
        elif status == 'pending':
            qs = qs.filter(is_approved=False)
        return qs


class AdminReviewApproveView(PanelPermissionMixin, View):
    permission_required = 'store.change_productreview'
    def post(self, request, pk):
        review = get_object_or_404(ProductReview, pk=pk)
        review.is_approved = True
        review.save(update_fields=['is_approved'])
        return redirect('admin_panel:review_list')


class AdminReviewDeleteView(PanelPermissionMixin, View):
    permission_required = 'store.delete_productreview'
    def post(self, request, pk):
        get_object_or_404(ProductReview, pk=pk).delete()
        return redirect('admin_panel:review_list')


# ─── Inventory ───────────────────────────────────────────────

class AdminInventoryListView(PanelPermissionMixin, ListView):
    permission_required = 'inventory.view_inventoryentry'
    template_name = 'admin_panel/inventory/inventory_list.html'
    context_object_name = 'entries'
    paginate_by = 30

    def get_queryset(self):
        qs = InventoryEntry.objects.select_related('product', 'created_by').order_by('-created_at')
        entry_type = self.request.GET.get('type', '')
        if entry_type in ('in', 'out'):
            qs = qs.filter(entry_type=entry_type)
        return qs


class AdminInventoryCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'inventory.add_inventoryentry'
    model = InventoryEntry
    form_class = InventoryEntryForm
    template_name = 'admin_panel/inventory/inventory_form.html'
    success_url = reverse_lazy('admin_panel:inventory_list')

    def form_valid(self, form):
        try:
            entry = record_movement(
                form.cleaned_data['product'],
                form.cleaned_data['entry_type'],
                form.cleaned_data['quantity'],
                user=self.request.user,
                supplier=form.cleaned_data.get('supplier', ''),
                reference=form.cleaned_data.get('reference', ''),
                notes=form.cleaned_data.get('notes', ''),
                unit_cost=form.cleaned_data.get('unit_cost') or 0,
            )
        except StockError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        if entry.entry_type == 'in':
            try:
                from telegram_bot.service import send_product_notification
                send_product_notification(entry.product)
            except Exception:
                pass
        return redirect(self.success_url)


class AdminInventoryReportView(PanelPermissionMixin, TemplateView):
    permission_required = 'inventory.view_inventoryentry'
    template_name = 'admin_panel/inventory/inventory_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        products = Product.objects.filter(is_active=True).select_related('category').order_by('stock')
        ctx['products'] = products
        ctx['total_products'] = products.count()
        ctx['out_of_stock'] = products.filter(stock=0).count()
        ctx['low_stock'] = products.filter(stock__gt=0, stock__lte=F('reorder_point')).count()
        return ctx


class AdminProductKardexView(PanelPermissionMixin, DetailView):
    """Full stock ledger (کاردکس) of one product."""
    permission_required = 'inventory.view_inventoryentry'
    model = Product
    template_name = 'admin_panel/inventory/kardex.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['entries'] = (self.object.inventory_entries
                          .select_related('created_by')
                          .order_by('-created_at', '-id')[:200])
        return ctx


class AdminProductExportView(PanelPermissionMixin, View):
    permission_required = 'store.view_product'

    def get(self, request):
        from finance.excel import workbook_response
        products = Product.objects.select_related('category').order_by('code')
        headers = ['کد کالا', 'نام', 'دسته‌بندی', 'واحد', 'قیمت فروش (ریال)',
                   'قیمت خرید (ریال)', 'موجودی', 'نقطه سفارش', 'بارکد', 'وضعیت']
        rows = [[p.code, p.name, str(p.category), p.unit, p.price, p.purchase_price,
                 p.stock, p.reorder_point, p.barcode or '', 'فعال' if p.is_active else 'غیرفعال']
                for p in products]
        return workbook_response('products', 'محصولات', headers, rows)


class AdminProductImportView(PanelPermissionMixin, View):
    """Excel import: columns کد کالا | نام | دسته‌بندی | واحد | قیمت فروش | قیمت خرید | نقطه سفارش | بارکد

    Existing products (matched by code) get price/unit/reorder updates; new
    ones are created. Stock is intentionally NOT importable — stock changes
    must go through inventory movements.
    """
    permission_required = 'store.add_product'

    @transaction.atomic
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            messages.error(request, 'فایل اکسل انتخاب نشده است.')
            return redirect('admin_panel:product_list')
        from django.utils.text import slugify

        from finance.excel import read_sheet
        try:
            _, rows = read_sheet(file_obj)
        except Exception:
            messages.error(request, 'فایل اکسل قابل خواندن نیست.')
            return redirect('admin_panel:product_list')

        created = updated = skipped = 0
        for row in rows:
            row = list(row) + [''] * (8 - len(row))
            code = str(row[0] or '').strip()
            name = str(row[1] or '').strip()
            if not name:
                skipped += 1
                continue

            def as_int(value, default=0):
                try:
                    return max(0, int(float(value)))
                except (TypeError, ValueError):
                    return default

            category = None
            cat_name = str(row[2] or '').strip()
            if cat_name:
                category = Category.objects.filter(name=cat_name.split('→')[-1].strip()).first()

            product = Product.objects.filter(code=code).first() if code else None
            if product:
                product.name = name
                if category:
                    product.category = category
                product.unit = str(row[3] or '').strip() or product.unit
                product.price = as_int(row[4], product.price)
                product.purchase_price = as_int(row[5], product.purchase_price)
                product.reorder_point = as_int(row[6], product.reorder_point)
                product.save()
                updated += 1
            else:
                if category is None:
                    category = Category.objects.filter(is_active=True).first()
                if category is None:
                    skipped += 1
                    continue
                slug = slugify(name, allow_unicode=True)
                if Product.objects.filter(slug=slug).exists():
                    slug = f'{slug}-{Product.objects.count() + 1}'
                Product.objects.create(
                    code=code or None,
                    name=name,
                    slug=slug,
                    category=category,
                    unit=str(row[3] or '').strip() or 'عدد',
                    price=as_int(row[4]),
                    purchase_price=as_int(row[5]),
                    reorder_point=as_int(row[6], 5),
                    barcode=str(row[7] or '').strip() or None,
                )
                created += 1
        messages.success(request, f'{created} محصول جدید، {updated} بروزرسانی ({skipped} رد شد).')
        return redirect('admin_panel:product_list')


# ─── Invoices ────────────────────────────────────────────────

def _parse_invoice_items(request):
    """Parse posted line-item arrays into dicts (server re-validates everything)."""
    from finance.text import parse_int
    products = request.POST.getlist('item_product')
    descriptions = request.POST.getlist('item_description')
    quantities = request.POST.getlist('item_qty')
    prices = request.POST.getlist('item_price')
    discounts = request.POST.getlist('item_discount')
    vats = request.POST.getlist('item_vat')
    items = []
    for i in range(len(quantities)):
        pid = (products[i] if i < len(products) else '').strip()
        description = (descriptions[i] if i < len(descriptions) else '').strip()
        qty = parse_int(quantities[i], 0)
        if not pid and not description:
            continue  # empty row
        product = None
        if pid:
            product = Product.objects.filter(pk=parse_int(pid, -1)).first()
            if product is None:
                raise InvoiceError('محصول انتخاب‌شده معتبر نیست.')
        vat_raw = (vats[i] if i < len(vats) else '').strip()
        items.append({
            'product': product,
            'description': description,
            'quantity': qty,
            'unit_price': parse_int(prices[i] if i < len(prices) else 0, 0),
            'discount': parse_int(discounts[i] if i < len(discounts) else 0, 0),
            'vat_rate': parse_int(vat_raw, 0) if vat_raw else None,
            'unit': product.unit if product else '',
        })
    if not items:
        raise InvoiceError('فاکتور باید حداقل یک قلم داشته باشد.')
    for item in items:
        if item['quantity'] <= 0:
            raise InvoiceError('تعداد هر قلم باید بزرگ‌تر از صفر باشد.')
        if item['unit_price'] <= 0:
            raise InvoiceError('قیمت واحد هر قلم باید بزرگ‌تر از صفر باشد.')
    return items


def _resolve_party(request):
    """Selected existing party, or quick-created one from name+mobile."""
    party_id = request.POST.get('party_id', '').strip()
    if party_id == 'new':
        name = request.POST.get('new_party_name', '').strip()
        if not name:
            raise InvoiceError('نام طرف حساب جدید را وارد کنید.')
        mobile = request.POST.get('new_party_mobile', '').strip()
        existing = Party.objects.filter(mobile=mobile).first() if mobile else None
        if existing:
            return existing
        party = Party.objects.create(name=name, mobile=mobile, party_type='customer')
        log_action(request.user, 'create', party)
        return party
    from finance.text import parse_int
    party = Party.objects.filter(pk=parse_int(party_id, -1), is_active=True).first()
    if party is None:
        raise InvoiceError('طرف حساب را انتخاب کنید.')
    return party


class AdminInvoiceListView(PanelPermissionMixin, ListView):
    permission_required = 'orders.view_invoice'
    template_name = 'admin_panel/invoices/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        from finance.text import parse_jalali_date
        qs = Invoice.objects.select_related('party')
        params = self.request.GET
        q = params.get('q', '').strip()
        if q:
            qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q)
                           | Q(party__name__icontains=q) | Q(party__mobile__icontains=q))
        if params.get('type') in dict(Invoice.DOC_TYPE_CHOICES):
            qs = qs.filter(doc_type=params['type'])
        if params.get('status') in dict(Invoice.STATUS_CHOICES):
            qs = qs.filter(status=params['status'])
        paid = params.get('paid', '')
        if paid == 'yes':
            qs = qs.filter(is_paid=True)
        elif paid == 'no':
            qs = qs.filter(is_paid=False)
        date_from = parse_jalali_date(params.get('from', ''))
        date_to = parse_jalali_date(params.get('to', ''))
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from.togregorian())
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to.togregorian())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doc_type_choices'] = Invoice.DOC_TYPE_CHOICES
        ctx['status_choices'] = Invoice.STATUS_CHOICES
        for key in ('q', 'type', 'status', 'paid', 'from', 'to'):
            ctx[f'f_{key}'] = self.request.GET.get(key, '')
        ctx['querystring'] = self.request.GET.urlencode()
        return ctx


class AdminInvoiceExportView(AdminInvoiceListView):
    """Excel export of the current filter set."""

    def render_to_response(self, context, **response_kwargs):
        from finance.excel import workbook_response
        headers = ['شماره', 'نوع', 'وضعیت', 'طرف حساب', 'تاریخ', 'جمع اقلام (ریال)',
                   'تخفیف (ریال)', 'مالیات (ریال)', 'جمع کل (ریال)', 'پرداختی (ریال)', 'تسویه']
        rows = [[inv.invoice_number, inv.get_doc_type_display(), inv.get_status_display(),
                 inv.customer_name or (inv.party.name if inv.party else ''),
                 inv.created_at.strftime('%Y/%m/%d') if inv.created_at else '',
                 inv.subtotal, inv.items_discount + inv.discount, inv.tax, inv.total,
                 inv.paid_amount, 'بله' if inv.is_paid else 'خیر']
                for inv in self.object_list]
        return workbook_response('invoices', 'فاکتورها', headers, rows)

    def get_paginate_by(self, queryset):
        return None


class _InvoiceFormMixin:
    """Shared context + POST handling for the create/edit screens."""
    template_name = 'admin_panel/invoices/invoice_form.html'

    def _form_context(self, request, invoice=None, doc_type='sale'):
        products = Product.objects.filter(is_active=True).order_by('name')
        initial_items = []
        if invoice:
            for item in invoice.items.all():
                initial_items.append({
                    'product': item.product_id or '',
                    'description': item.description,
                    'qty': item.quantity,
                    'price': item.unit_price,
                    'discount': item.discount,
                    'vat': '' if item.vat_rate is None else item.vat_rate,
                })
        from admin_panel.models import SiteSetting
        return {
            'invoice': invoice,
            'doc_type': invoice.doc_type if invoice else doc_type,
            'doc_type_choices': Invoice.DOC_TYPE_CHOICES,
            'settlement_choices': Invoice.SETTLEMENT_CHOICES,
            'products': products,
            'parties': Party.objects.filter(is_active=True).order_by('name'),
            'default_vat_rate': invoice.vat_rate if invoice else SiteSetting.load().vat_rate,
            'initial_items': json.dumps(initial_items, ensure_ascii=False),
            'submission_token': uuid.uuid4(),
            'page_title': (f'ویرایش {invoice.invoice_number}' if invoice else 'سند جدید'),
        }

    def _apply_post(self, request, invoice):
        """Write posted header + items onto a draft invoice and recompute."""
        from finance.text import parse_int, parse_jalali_date
        items = _parse_invoice_items(request)
        invoice.party = _resolve_party(request)
        invoice.customer_name = invoice.party.name
        invoice.customer_mobile = invoice.party.mobile
        invoice.customer_address = invoice.party.address
        invoice.discount = parse_int(request.POST.get('discount'), 0)
        invoice.vat_rate = parse_int(request.POST.get('vat_rate'), 0)
        invoice.settlement_type = (request.POST.get('settlement_type')
                                   if request.POST.get('settlement_type') in dict(Invoice.SETTLEMENT_CHOICES)
                                   else 'cash')
        if invoice.settlement_type == 'cash':
            invoice.paid_amount = 0  # normalized to full total at issue below
        else:
            invoice.paid_amount = parse_int(request.POST.get('paid_amount'), 0)
        invoice.due_date = parse_jalali_date(request.POST.get('due_date', ''))
        invoice.notes = request.POST.get('notes', '')
        invoice.save()
        invoice.items.all().delete()
        for item in items:
            InvoiceItem.objects.create(invoice=invoice, **item)
        recompute_totals(invoice)
        if invoice.settlement_type == 'cash':
            invoice.paid_amount = invoice.total
            invoice.save(update_fields=['paid_amount'])
        return invoice


class AdminInvoiceCreateView(PanelPermissionMixin, _InvoiceFormMixin, View):
    permission_required = 'orders.add_invoice'

    def get(self, request):
        from django.shortcuts import render
        doc_type = request.GET.get('type', 'sale')
        if doc_type not in dict(Invoice.DOC_TYPE_CHOICES):
            doc_type = 'sale'
        return render(request, self.template_name, self._form_context(request, doc_type=doc_type))

    def post(self, request):
        token = request.POST.get('submission_token') or None
        if token:
            existing = Invoice.objects.filter(submission_token=token).first()
            if existing:  # double submit → same document, no double issue
                return redirect('admin_panel:invoice_detail', pk=existing.pk)
        doc_type = request.POST.get('doc_type', 'sale')
        if doc_type not in dict(Invoice.DOC_TYPE_CHOICES):
            doc_type = 'sale'
        invoice = Invoice(doc_type=doc_type, status='draft', submission_token=token)
        try:
            with transaction.atomic():
                self._apply_post(request, invoice)
                if request.POST.get('action') == 'issue':
                    if not request.user.has_perm('orders.change_invoice'):
                        raise InvoiceError('دسترسی صدور سند را ندارید.')
                    invoice = issue_invoice(invoice, request.user)
                    messages.success(request, f'سند {invoice.invoice_number} صادر شد.')
                else:
                    log_action(request.user, 'create', invoice)
                    messages.success(request, 'پیش‌نویس ذخیره شد.')
        except (InvoiceError, StockError, LedgerError) as exc:
            messages.error(request, str(exc))
            from django.shortcuts import render
            return render(request, self.template_name, self._form_context(request, doc_type=doc_type))
        return redirect('admin_panel:invoice_detail', pk=invoice.pk)


class AdminInvoiceEditView(PanelPermissionMixin, _InvoiceFormMixin, View):
    permission_required = 'orders.change_invoice'

    def get_invoice(self, pk):
        return get_object_or_404(Invoice.objects.prefetch_related('items__product'), pk=pk)

    def get(self, request, pk):
        from django.shortcuts import render
        invoice = self.get_invoice(pk)
        if not invoice.is_editable:
            messages.error(request, 'فقط پیش‌نویس‌ها قابل ویرایش هستند؛ سند صادرشده را باطل کنید.')
            return redirect('admin_panel:invoice_detail', pk=invoice.pk)
        return render(request, self.template_name, self._form_context(request, invoice=invoice))

    def post(self, request, pk):
        invoice = self.get_invoice(pk)
        if not invoice.is_editable:
            messages.error(request, 'فقط پیش‌نویس‌ها قابل ویرایش هستند.')
            return redirect('admin_panel:invoice_detail', pk=invoice.pk)
        before = model_snapshot(invoice)
        try:
            with transaction.atomic():
                self._apply_post(request, invoice)
                if request.POST.get('action') == 'issue':
                    invoice = issue_invoice(invoice, request.user)
                    messages.success(request, f'سند {invoice.invoice_number} صادر شد.')
                else:
                    log_action(request.user, 'update', invoice, before=before, after=model_snapshot(invoice))
                    messages.success(request, 'پیش‌نویس بروزرسانی شد.')
        except (InvoiceError, StockError, LedgerError) as exc:
            messages.error(request, str(exc))
            from django.shortcuts import render
            invoice.refresh_from_db()
            return render(request, self.template_name, self._form_context(request, invoice=invoice))
        return redirect('admin_panel:invoice_detail', pk=invoice.pk)


class AdminInvoiceDetailView(PanelPermissionMixin, DetailView):
    permission_required = 'orders.view_invoice'
    model = Invoice
    template_name = 'admin_panel/invoices/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.select_related('party', 'issued_by').prefetch_related('items__product')


class AdminInvoiceIssueView(PanelPermissionMixin, View):
    permission_required = 'orders.change_invoice'

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            invoice = issue_invoice(invoice, request.user)
            messages.success(request, f'سند {invoice.invoice_number} صادر شد.')
        except (InvoiceError, StockError, LedgerError) as exc:
            messages.error(request, str(exc))
        return redirect('admin_panel:invoice_detail', pk=pk)


class AdminInvoiceCancelView(PanelPermissionMixin, View):
    permission_required = 'orders.delete_invoice'

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            invoice = cancel_invoice(invoice, request.user)
            messages.success(request, f'سند {invoice.invoice_number} باطل شد و آثار مالی آن برگشت خورد.')
        except (InvoiceError, StockError) as exc:
            messages.error(request, str(exc))
        return redirect('admin_panel:invoice_detail', pk=pk)


class AdminInvoiceDeleteView(PanelPermissionMixin, View):
    """Hard delete is for drafts only; issued documents go through cancel."""
    permission_required = 'orders.delete_invoice'

    @transaction.atomic
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if invoice.status != 'draft':
            messages.error(request, 'سند صادرشده حذف نمی‌شود؛ آن را باطل کنید.')
            return redirect('admin_panel:invoice_detail', pk=pk)
        log_action(request.user, 'delete', invoice, before=model_snapshot(invoice))
        invoice.delete()
        messages.success(request, 'پیش‌نویس حذف شد.')
        return redirect('admin_panel:invoice_list')


class AdminInvoicePDFView(PanelPermissionMixin, View):
    """?official=1 → official layout (VAT/legal fields), else simple receipt."""
    permission_required = 'orders.view_invoice'

    def get(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related('party').prefetch_related('items__product'), pk=pk)
        official = request.GET.get('official') == '1'
        template = 'orders/invoice_pdf_official.html' if official else 'orders/invoice_pdf.html'
        from admin_panel.models import SiteSetting
        html = render_to_string(template, {
            'invoice': invoice,
            'site': SiteSetting.load(),
        }, request=request)
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        label = 'official' if official else 'receipt'
        response['Content-Disposition'] = f'inline; filename="invoice-{invoice.invoice_number}-{label}.pdf"'
        return response


# ─── Parties (طرف حساب‌ها) ───────────────────────────────────

def _party_balance_annotation():
    return (Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=LedgerEntry.DEBIT), default=0)
            - Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=LedgerEntry.CREDIT), default=0))


class AdminPartyListView(PanelPermissionMixin, ListView):
    permission_required = 'parties.view_party'
    template_name = 'admin_panel/parties/party_list.html'
    context_object_name = 'parties'
    paginate_by = 20

    def get_queryset(self):
        qs = (Party.objects.prefetch_related('tags')
              .annotate(balance_amount=_party_balance_annotation()).order_by('name'))
        q = self.request.GET.get('q', '').strip()
        party_type = self.request.GET.get('type', '').strip()
        tag = self.request.GET.get('tag', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(company__icontains=q) | Q(mobile__icontains=q))
        if party_type in dict(Party.TYPE_CHOICES):
            qs = qs.filter(party_type=party_type)
        if tag:
            qs = qs.filter(tags__pk=tag)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['type_choices'] = Party.TYPE_CHOICES
        ctx['all_tags'] = PartyTag.objects.all()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_tag'] = self.request.GET.get('tag', '')
        return ctx


class AdminPartyCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'parties.add_party'
    template_name = 'admin_panel/parties/party_form.html'
    form_class = PartyForm
    success_url = reverse_lazy('admin_panel:party_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, 'create', self.object)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'افزودن طرف حساب'
        return ctx


class AdminPartyEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'parties.change_party'
    model = Party
    template_name = 'admin_panel/parties/party_form.html'
    form_class = PartyForm
    success_url = reverse_lazy('admin_panel:party_list')

    def form_valid(self, form):
        before = model_snapshot(self.model.objects.get(pk=self.object.pk))
        response = super().form_valid(form)
        log_action(self.request.user, 'update', self.object, before=before, after=model_snapshot(self.object))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'ویرایش طرف حساب'
        return ctx


class AdminPartyLedgerView(PanelPermissionMixin, DetailView):
    """Party profile + full ledger with running balance + payment entry."""
    permission_required = 'parties.view_ledgerentry'
    model = Party
    template_name = 'admin_panel/parties/party_ledger.html'
    context_object_name = 'party'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = ledger_rows_with_balance(self.object)
        ctx['rows'] = rows
        ctx['balance'] = rows[-1]['balance'] if rows else 0
        ctx['total_debit'] = sum(r['entry'].amount for r in rows if r['entry'].entry_type == LedgerEntry.DEBIT)
        ctx['total_credit'] = sum(r['entry'].amount for r in rows if r['entry'].entry_type == LedgerEntry.CREDIT)
        ctx['payment_form'] = PaymentForm()
        return ctx


class AdminPaymentCreateView(PanelPermissionMixin, View):
    permission_required = 'parties.add_payment'

    def post(self, request, pk):
        party = get_object_or_404(Party, pk=pk)
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                record_payment(
                    party=party,
                    kind=form.cleaned_data['kind'],
                    method=form.cleaned_data['method'],
                    amount=form.cleaned_data['amount'],
                    reference=form.cleaned_data['reference'],
                    description=form.cleaned_data['description'],
                    user=request.user,
                )
                messages.success(request, 'تراکنش با موفقیت ثبت شد.')
            except LedgerError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, 'اطلاعات فرم نامعتبر است.')
        return redirect('admin_panel:party_ledger', pk=party.pk)


class AdminPartyBalanceReportView(PanelPermissionMixin, ListView):
    """All parties with debit/credit totals and net balance."""
    permission_required = 'parties.view_party'
    template_name = 'admin_panel/parties/balance_report.html'
    context_object_name = 'parties'

    def get_queryset(self):
        return (Party.objects.filter(is_active=True)
                .annotate(balance_amount=_party_balance_annotation(),
                          total_debit=Sum('ledger_entries__amount',
                                          filter=Q(ledger_entries__entry_type=LedgerEntry.DEBIT), default=0),
                          total_credit=Sum('ledger_entries__amount',
                                           filter=Q(ledger_entries__entry_type=LedgerEntry.CREDIT), default=0))
                .order_by('-balance_amount'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        parties = list(ctx['parties'])
        ctx['sum_receivable'] = sum(p.balance_amount for p in parties if p.balance_amount > 0)
        ctx['sum_payable'] = -sum(p.balance_amount for p in parties if p.balance_amount < 0)
        return ctx


class AdminPartyBalanceReportPDFView(AdminPartyBalanceReportView):
    def render_to_response(self, context, **response_kwargs):
        context['pdf_mode'] = True
        html = render_to_string('admin_panel/parties/balance_report_pdf.html', context, request=self.request)
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="party-balances.pdf"'
        return response


class AdminPartyLedgerPDFView(PanelPermissionMixin, View):
    permission_required = 'parties.view_ledgerentry'

    def get(self, request, pk):
        party = get_object_or_404(Party, pk=pk)
        rows = ledger_rows_with_balance(party)
        balance = rows[-1]['balance'] if rows else 0
        html = render_to_string('admin_panel/parties/party_ledger_pdf.html', {
            'party': party,
            'rows': rows,
            'balance': balance,
            'abs_balance': abs(balance),
        }, request=request)
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="ledger-{party.pk}.pdf"'
        return response


class AdminPartyLedgerExportView(PanelPermissionMixin, View):
    permission_required = 'parties.view_ledgerentry'

    def get(self, request, pk):
        from finance.excel import workbook_response
        party = get_object_or_404(Party, pk=pk)
        rows = []
        for row in ledger_rows_with_balance(party):
            entry = row['entry']
            rows.append([
                entry.created_at.strftime('%Y/%m/%d %H:%M'),
                entry.description,
                entry.amount if entry.entry_type == LedgerEntry.DEBIT else '',
                entry.amount if entry.entry_type == LedgerEntry.CREDIT else '',
                row['balance'],
            ])
        headers = ['تاریخ', 'شرح', 'بدهکار (ریال)', 'بستانکار (ریال)', 'مانده (ریال)']
        return workbook_response(f'ledger-{party.pk}', f'دفتر {party.name}'[:31], headers, rows)


class AdminPartyExportView(PanelPermissionMixin, View):
    permission_required = 'parties.view_party'

    def get(self, request):
        from finance.excel import workbook_response
        parties = Party.objects.annotate(balance_amount=_party_balance_annotation()).order_by('name')
        headers = ['نام', 'نوع', 'شرکت', 'موبایل', 'تلفن', 'کد ملی', 'کد اقتصادی',
                   'استان', 'شهر', 'آدرس', 'مانده (ریال)', 'وضعیت']
        rows = [[p.name, p.get_party_type_display(), p.company, p.mobile, p.phone,
                 p.national_id, p.economic_code, p.province, p.city, p.address,
                 p.balance_amount, 'فعال' if p.is_active else 'غیرفعال'] for p in parties]
        return workbook_response('parties', 'طرف حساب‌ها', headers, rows)


class AdminPartyImportView(PanelPermissionMixin, View):
    """Excel import: columns نام | نوع | شرکت | موبایل | تلفن | کد ملی | کد اقتصادی | استان | شهر | آدرس"""
    permission_required = 'parties.add_party'

    TYPE_BY_LABEL = {label: value for value, label in Party.TYPE_CHOICES}

    @transaction.atomic
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            messages.error(request, 'فایل اکسل انتخاب نشده است.')
            return redirect('admin_panel:party_list')
        from finance.excel import read_sheet
        try:
            _, rows = read_sheet(file_obj)
        except Exception:
            messages.error(request, 'فایل اکسل قابل خواندن نیست.')
            return redirect('admin_panel:party_list')

        created = skipped = 0
        for row in rows:
            row = list(row) + [''] * (10 - len(row))
            name = str(row[0] or '').strip()
            if not name:
                skipped += 1
                continue
            mobile = str(row[3] or '').strip()
            exists = Party.objects.filter(mobile=mobile).exists() if mobile else Party.objects.filter(name=name).exists()
            if exists:
                skipped += 1
                continue
            party = Party.objects.create(
                name=name,
                party_type=self.TYPE_BY_LABEL.get(str(row[1] or '').strip(), 'customer'),
                company=str(row[2] or '').strip(),
                mobile=mobile,
                phone=str(row[4] or '').strip(),
                national_id=str(row[5] or '').strip(),
                economic_code=str(row[6] or '').strip(),
                province=str(row[7] or '').strip(),
                city=str(row[8] or '').strip(),
                address=str(row[9] or '').strip(),
            )
            log_action(request.user, 'create', party)
            created += 1
        messages.success(request, f'{created} طرف حساب وارد شد ({skipped} رد شد).')
        return redirect('admin_panel:party_list')


# ─── Cash flow (هزینه و درآمد) ───────────────────────────────

class AdminCashFlowView(PanelPermissionMixin, ListView):
    """Income/expense register + monthly cash-flow summary."""
    permission_required = 'finance.view_cashtransaction'
    template_name = 'admin_panel/cashflow/cashflow.html'
    context_object_name = 'transactions'
    paginate_by = 20

    def get_queryset(self):
        from finance.models import CashTransaction
        qs = CashTransaction.objects.select_related('category', 'created_by')
        params = self.request.GET
        if params.get('kind') in ('income', 'expense'):
            qs = qs.filter(kind=params['kind'])
        if params.get('category', '').isdigit():
            qs = qs.filter(category_id=params['category'])
        return qs

    def get_context_data(self, **kwargs):
        import jdatetime

        from finance.models import CashTransaction, ExpenseCategory
        ctx = super().get_context_data(**kwargs)
        today = jdatetime.date.today()

        # This Jalali month
        month_start = today.replace(day=1)
        month_qs = CashTransaction.objects.filter(date__gte=month_start, date__lte=today)
        ctx['month_income'] = month_qs.filter(kind='income').aggregate(t=Sum('amount'))['t'] or 0
        ctx['month_expense'] = month_qs.filter(kind='expense').aggregate(t=Sum('amount'))['t'] or 0
        ctx['month_net'] = ctx['month_income'] - ctx['month_expense']

        # Last 6 Jalali months (chart, Toman)
        labels, incomes, expenses = [], [], []
        year, month = today.year, today.month
        points = []
        for _ in range(6):
            points.append((year, month))
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        for y, m in reversed(points):
            start = jdatetime.date(y, m, 1)
            days = jdatetime.j_days_in_month[m - 1] + (1 if m == 12 and start.isleap() else 0)
            end = jdatetime.date(y, m, days)
            month_data = CashTransaction.objects.filter(date__gte=start, date__lte=end)
            labels.append(f'{y}/{m}')
            incomes.append((month_data.filter(kind='income').aggregate(t=Sum('amount'))['t'] or 0) // 10)
            expenses.append((month_data.filter(kind='expense').aggregate(t=Sum('amount'))['t'] or 0) // 10)
        ctx['flow_labels'] = json.dumps(labels)
        ctx['flow_income'] = json.dumps(incomes)
        ctx['flow_expense'] = json.dumps(expenses)

        ctx['form'] = CashTransactionForm()
        ctx['category_form'] = ExpenseCategoryForm()
        ctx['categories'] = ExpenseCategory.objects.filter(is_active=True)
        ctx['f_kind'] = self.request.GET.get('kind', '')
        ctx['f_category'] = self.request.GET.get('category', '')
        return ctx


class AdminCashTransactionCreateView(PanelPermissionMixin, View):
    permission_required = 'finance.add_cashtransaction'

    def post(self, request):
        form = CashTransactionForm(request.POST)
        if form.is_valid():
            tx = form.save(commit=False)
            tx.created_by = request.user
            tx.save()
            log_action(request.user, 'create', tx)
            messages.success(request, 'تراکنش ثبت شد.')
        else:
            messages.error(request, ' — '.join(e for errs in form.errors.values() for e in errs))
        return redirect('admin_panel:cashflow')


class AdminCashTransactionDeleteView(PanelPermissionMixin, View):
    permission_required = 'finance.delete_cashtransaction'

    def post(self, request, pk):
        from finance.models import CashTransaction
        tx = get_object_or_404(CashTransaction, pk=pk)
        log_action(request.user, 'delete', tx, before=model_snapshot(tx))
        tx.delete()
        messages.success(request, 'تراکنش حذف شد.')
        return redirect('admin_panel:cashflow')


class AdminExpenseCategoryCreateView(PanelPermissionMixin, View):
    permission_required = 'finance.add_expensecategory'

    def post(self, request):
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'دسته جدید ساخته شد.')
        else:
            messages.error(request, 'نام دسته تکراری یا نامعتبر است.')
        return redirect('admin_panel:cashflow')


# ─── Cheques (چک‌ها) ─────────────────────────────────────────

class AdminChequeListView(PanelPermissionMixin, ListView):
    permission_required = 'cheques.view_cheque'
    template_name = 'admin_panel/cheques/cheque_list.html'
    context_object_name = 'cheques'
    paginate_by = 20

    def get_queryset(self):
        qs = Cheque.objects.select_related('party', 'invoice')
        params = self.request.GET
        if params.get('direction') in dict(Cheque.DIRECTION_CHOICES):
            qs = qs.filter(direction=params['direction'])
        if params.get('status') in dict(Cheque.STATUS_CHOICES):
            qs = qs.filter(status=params['status'])
        q = params.get('q', '').strip()
        if q:
            qs = qs.filter(Q(serial__icontains=q) | Q(sayad_id__icontains=q)
                           | Q(party__name__icontains=q) | Q(bank_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        import jdatetime
        ctx = super().get_context_data(**kwargs)
        ctx['direction_choices'] = Cheque.DIRECTION_CHOICES
        ctx['status_choices'] = Cheque.STATUS_CHOICES
        ctx['today'] = jdatetime.date.today()
        for key in ('q', 'direction', 'status'):
            ctx[f'f_{key}'] = self.request.GET.get(key, '')
        return ctx


class AdminChequeCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'cheques.add_cheque'
    form_class = ChequeForm
    template_name = 'admin_panel/cheques/cheque_form.html'
    success_url = reverse_lazy('admin_panel:cheque_list')

    def get_initial(self):
        initial = super().get_initial()
        for key in ('party', 'invoice', 'direction'):
            if self.request.GET.get(key):
                initial[key] = self.request.GET[key]
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'create', self.object)
        messages.success(self.request, 'چک ثبت شد.')
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'ثبت چک جدید'
        return ctx


class AdminChequeEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'cheques.change_cheque'
    model = Cheque
    form_class = ChequeForm
    template_name = 'admin_panel/cheques/cheque_form.html'
    success_url = reverse_lazy('admin_panel:cheque_list')

    def dispatch(self, request, *args, **kwargs):
        cheque = self.get_object()
        if cheque.status != 'pending' and request.user.is_authenticated and request.user.is_staff:
            messages.error(request, 'چک وصول‌شده/برگشتی قابل ویرایش نیست.')
            return redirect('admin_panel:cheque_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        before = model_snapshot(self.model.objects.get(pk=self.object.pk))
        response = super().form_valid(form)
        log_action(self.request.user, 'update', self.object, before=before, after=model_snapshot(self.object))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = f'ویرایش چک {self.object.serial}'
        return ctx


class AdminChequeStatusView(PanelPermissionMixin, View):
    permission_required = 'cheques.change_cheque'

    def post(self, request, pk):
        cheque = get_object_or_404(Cheque, pk=pk)
        try:
            cheque = set_cheque_status(cheque, request.POST.get('status', ''), request.user)
            messages.success(request, f'چک {cheque.serial}: {cheque.get_status_display()}.')
        except ChequeError as exc:
            messages.error(request, str(exc))
        return redirect(request.META.get('HTTP_REFERER') or 'admin_panel:cheque_list')


class AdminChequeDueReportView(PanelPermissionMixin, TemplateView):
    permission_required = 'cheques.view_cheque'
    template_name = 'admin_panel/cheques/due_report.html'

    def get_context_data(self, **kwargs):
        import datetime

        import jdatetime
        ctx = super().get_context_data(**kwargs)
        today = jdatetime.date.today()
        horizon = today + datetime.timedelta(days=30)
        pending = Cheque.objects.filter(status='pending').select_related('party')
        ctx['overdue'] = pending.filter(due_date__lt=today)
        ctx['upcoming'] = pending.filter(due_date__gte=today, due_date__lte=horizon)
        ctx['overdue_received'] = sum(c.amount for c in ctx['overdue'] if c.direction == 'received')
        ctx['overdue_issued'] = sum(c.amount for c in ctx['overdue'] if c.direction == 'issued')
        ctx['upcoming_received'] = sum(c.amount for c in ctx['upcoming'] if c.direction == 'received')
        ctx['upcoming_issued'] = sum(c.amount for c in ctx['upcoming'] if c.direction == 'issued')
        ctx['today'] = today
        return ctx


class AdminChequePrintView(PanelPermissionMixin, DetailView):
    """Browser-print page positioned by the bank's stored offsets."""
    permission_required = 'cheques.view_cheque'
    model = Cheque
    template_name = 'admin_panel/cheques/cheque_print.html'
    context_object_name = 'cheque'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        layout, _ = ChequePrintLayout.objects.get_or_create(bank_name=self.object.bank_name)
        ctx['layout'] = layout
        return ctx


class AdminChequeLayoutEditView(PanelPermissionMixin, View):
    """Adjust the per-bank x/y print offsets for a cheque's bank."""
    permission_required = 'cheques.change_chequeprintlayout'
    template_name = 'admin_panel/cheques/layout_form.html'

    def get_layout(self, pk):
        cheque = get_object_or_404(Cheque, pk=pk)
        layout, _ = ChequePrintLayout.objects.get_or_create(bank_name=cheque.bank_name)
        return cheque, layout

    def get(self, request, pk):
        from django.shortcuts import render
        cheque, layout = self.get_layout(pk)
        return render(request, self.template_name, {
            'cheque': cheque,
            'form': ChequePrintLayoutForm(instance=layout),
            'page_title': f'قالب چاپ {layout.bank_name}',
        })

    def post(self, request, pk):
        from django.shortcuts import render
        cheque, layout = self.get_layout(pk)
        form = ChequePrintLayoutForm(request.POST, instance=layout)
        if form.is_valid():
            form.save()
            messages.success(request, 'قالب چاپ ذخیره شد.')
            return redirect('admin_panel:cheque_print', pk=cheque.pk)
        return render(request, self.template_name, {'cheque': cheque, 'form': form,
                                                    'page_title': f'قالب چاپ {layout.bank_name}'})


class AdminChequeBookListView(PanelPermissionMixin, ListView):
    permission_required = 'cheques.view_chequebook'
    template_name = 'admin_panel/cheques/book_list.html'
    context_object_name = 'books'

    def get_queryset(self):
        return ChequeBook.objects.annotate(cheque_count=Count('cheques'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = ChequeBookForm()
        return ctx


class AdminChequeBookCreateView(PanelPermissionMixin, View):
    permission_required = 'cheques.add_chequebook'

    def post(self, request):
        form = ChequeBookForm(request.POST)
        if form.is_valid():
            book = form.save()
            log_action(request.user, 'create', book)
            messages.success(request, 'دسته‌چک ثبت شد.')
        else:
            messages.error(request, 'اطلاعات دسته‌چک نامعتبر است.')
        return redirect('admin_panel:chequebook_list')


class AdminChequeBookToggleView(PanelPermissionMixin, View):
    permission_required = 'cheques.change_chequebook'

    def post(self, request, pk):
        book = get_object_or_404(ChequeBook, pk=pk)
        book.is_active = not book.is_active
        book.save(update_fields=['is_active'])
        log_action(request.user, 'status', book)
        return redirect('admin_panel:chequebook_list')


# ─── Blog ────────────────────────────────────────────────────

class AdminPostListView(PanelPermissionMixin, ListView):
    permission_required = 'blog.view_blogpost'
    template_name = 'admin_panel/blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 20

    def get_queryset(self):
        return BlogPost.objects.select_related('author').order_by('-created_at')


class AdminPostCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'blog.add_blogpost'
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'admin_panel/blog/post_form.html'
    success_url = reverse_lazy('admin_panel:post_list')

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'نوشتن مقاله'
        return ctx


class AdminPostEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'blog.change_blogpost'
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'admin_panel/blog/post_form.html'
    success_url = reverse_lazy('admin_panel:post_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['page_title'] = 'ویرایش مقاله'
        return ctx


class AdminPostDeleteView(PanelPermissionMixin, View):
    permission_required = 'blog.delete_blogpost'
    def post(self, request, pk):
        get_object_or_404(BlogPost, pk=pk).delete()
        return redirect('admin_panel:post_list')


class AdminPostTogglePublishView(PanelPermissionMixin, View):
    permission_required = 'blog.change_blogpost'
    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        post.is_published = not post.is_published
        post.save(update_fields=['is_published'])
        return redirect('admin_panel:post_list')


class AdminAnnouncementListView(PanelPermissionMixin, ListView):
    permission_required = 'blog.view_announcement'
    template_name = 'admin_panel/blog/announcement_list.html'
    context_object_name = 'announcements'

    def get_queryset(self):
        return Announcement.objects.order_by('-created_at')


class AdminAnnouncementCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'blog.add_announcement'
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'admin_panel/blog/announcement_form.html'
    success_url = reverse_lazy('admin_panel:announcement_list')


class AdminAnnouncementEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'blog.change_announcement'
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'admin_panel/blog/announcement_form.html'
    success_url = reverse_lazy('admin_panel:announcement_list')


class AdminAnnouncementDeleteView(PanelPermissionMixin, View):
    permission_required = 'blog.delete_announcement'
    def post(self, request, pk):
        get_object_or_404(Announcement, pk=pk).delete()
        return redirect('admin_panel:announcement_list')


# ─── Users ───────────────────────────────────────────────────

class AdminUserListView(PanelPermissionMixin, ListView):
    permission_required = 'accounts.view_user'
    template_name = 'admin_panel/users/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.annotate(order_count=Count('orders')).order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(mobile__icontains=q))
        return qs


class AdminStaffListView(PanelPermissionMixin, ListView):
    permission_required = 'accounts.view_staffprofile'
    template_name = 'admin_panel/users/staff_list.html'
    context_object_name = 'staff_members'

    def get_queryset(self):
        return StaffProfile.objects.select_related('user').order_by('-is_active_staff')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['role_choices'] = StaffProfile.ROLE_CHOICES
        return ctx


class AdminStaffCreateView(PanelPermissionMixin, View):
    permission_required = 'accounts.add_staffprofile'
    @transaction.atomic
    def post(self, request):
        form = StaffForm(request.POST)
        if form.is_valid():
            mobile = form.cleaned_data['mobile']
            role = form.cleaned_data['role']
            user, _ = User.objects.get_or_create(mobile=mobile, defaults={'username': mobile})
            user.is_staff = True
            user.save(update_fields=['is_staff'])
            profile, created = StaffProfile.objects.get_or_create(
                user=user, defaults={'role': role, 'is_active_staff': True})
            role_changed = not created and profile.role != role
            if not created:
                profile.role = role
                profile.is_active_staff = True
                profile.save(update_fields=['role', 'is_active_staff'])
            if created or role_changed:
                # New role → reset permissions to that role's defaults;
                # fine-tuning happens on the permissions screen afterwards.
                panel_permissions.apply_role_defaults(user, role)
            log_action(request.user, 'create' if created else 'update', profile)
        return redirect('admin_panel:staff_list')


class AdminStaffDeleteView(PanelPermissionMixin, View):
    permission_required = 'accounts.delete_staffprofile'
    @transaction.atomic
    def post(self, request, pk):
        sp = get_object_or_404(StaffProfile, pk=pk)
        before = model_snapshot(sp)
        sp.is_active_staff = False
        sp.save(update_fields=['is_active_staff'])
        sp.user.is_staff = False
        sp.user.save(update_fields=['is_staff'])
        log_action(request.user, 'status', sp, before=before, after=model_snapshot(sp))
        return redirect('admin_panel:staff_list')


class AdminStaffPermissionsView(PanelPermissionMixin, View):
    """Grant/revoke per-module permissions for one staff member."""
    permission_required = 'accounts.change_user'
    template_name = 'admin_panel/users/staff_permissions.html'

    def get(self, request, pk):
        sp = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
        return self._render(request, sp)

    @transaction.atomic
    def post(self, request, pk):
        sp = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
        user = sp.user
        if user.is_superuser:
            messages.error(request, 'دسترسی مدیر ارشد قابل ویرایش نیست.')
            return redirect('admin_panel:staff_list')
        before = {'permissions': panel_permissions.granted_cells(user)}
        perms = []
        for module in panel_permissions.MODULES:
            for action in panel_permissions.module_actions(module):
                if request.POST.get(f'{module}:{action}'):
                    perms.extend(panel_permissions.get_permissions(module, action))
        user.user_permissions.set(perms)
        user = User.objects.get(pk=user.pk)  # fresh instance: has_perm caches per object
        log_action(request.user, 'update', user,
                   before=before, after={'permissions': panel_permissions.granted_cells(user)})
        messages.success(request, 'دسترسی‌ها ذخیره شد.')
        return redirect('admin_panel:staff_permissions', pk=sp.pk)

    def _render(self, request, sp):
        from django.shortcuts import render
        matrix = panel_permissions.user_matrix(sp.user)
        rows = []
        for module, cfg in panel_permissions.MODULES.items():
            available = panel_permissions.module_actions(module)
            rows.append({
                'key': module,
                'label': cfg['label'],
                'cells': [{
                    'action': action,
                    'label': panel_permissions.ACTION_LABELS[action],
                    'available': action in available,
                    'granted': matrix[module].get(action, False),
                } for action in panel_permissions.ACTIONS],
            })
        return render(request, self.template_name, {
            'staff': sp,
            'rows': rows,
            'action_labels': [panel_permissions.ACTION_LABELS[a] for a in panel_permissions.ACTIONS],
            'page_title': f'دسترسی‌های {sp.user}',
        })


class AdminAuditLogListView(PanelPermissionMixin, ListView):
    permission_required = 'finance.view_auditlog'
    template_name = 'admin_panel/audit/log_list.html'
    context_object_name = 'logs'
    paginate_by = 30

    def get_queryset(self):
        qs = AuditLog.objects.select_related('actor', 'content_type')
        action = self.request.GET.get('action', '').strip()
        if action in dict(AuditLog.ACTION_CHOICES):
            qs = qs.filter(action=action)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(object_repr__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action_choices'] = AuditLog.ACTION_CHOICES
        ctx['selected_action'] = self.request.GET.get('action', '')
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


# ─── Services & Projects ────────────────────────────────────

class AdminServiceListView(PanelPermissionMixin, ListView):
    permission_required = 'services.view_service'
    template_name = 'admin_panel/services/service_list.html'
    context_object_name = 'services'

    def get_queryset(self):
        return Service.objects.order_by('order')


class AdminServiceCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'services.add_service'
    model = Service
    form_class = ServiceForm
    template_name = 'admin_panel/services/service_form.html'
    success_url = reverse_lazy('admin_panel:service_list')


class AdminServiceEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'services.change_service'
    model = Service
    form_class = ServiceForm
    template_name = 'admin_panel/services/service_form.html'
    success_url = reverse_lazy('admin_panel:service_list')


class AdminServiceDeleteView(PanelPermissionMixin, View):
    permission_required = 'services.delete_service'
    def post(self, request, pk):
        get_object_or_404(Service, pk=pk).delete()
        return redirect('admin_panel:service_list')


class AdminProjectListView(PanelPermissionMixin, ListView):
    permission_required = 'services.view_project'
    template_name = 'admin_panel/services/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        return Project.objects.prefetch_related('images').order_by('-created_at')


class AdminProjectCreateView(PanelPermissionMixin, CreateView):
    permission_required = 'services.add_project'
    model = Project
    form_class = ProjectForm
    template_name = 'admin_panel/services/project_form.html'
    success_url = reverse_lazy('admin_panel:project_list')


class AdminProjectEditView(PanelPermissionMixin, UpdateView):
    permission_required = 'services.change_project'
    model = Project
    form_class = ProjectForm
    template_name = 'admin_panel/services/project_form.html'
    success_url = reverse_lazy('admin_panel:project_list')


class AdminProjectDeleteView(PanelPermissionMixin, View):
    permission_required = 'services.delete_project'
    def post(self, request, pk):
        get_object_or_404(Project, pk=pk).delete()
        return redirect('admin_panel:project_list')


# ─── Settings ────────────────────────────────────────────────

class AdminSiteSettingsView(PanelPermissionMixin, View):
    permission_required = 'admin_panel.change_sitesetting'
    template_name = 'admin_panel/settings/site_settings.html'

    def get(self, request):
        from django.shortcuts import render
        from .models import SiteSetting
        from .forms import SiteSettingForm
        form = SiteSettingForm(instance=SiteSetting.load())
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from .models import SiteSetting
        from .forms import SiteSettingForm
        instance = SiteSetting.load()
        before = model_snapshot(instance)
        form = SiteSettingForm(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save()
            log_action(request.user, 'update', obj, before=before, after=model_snapshot(obj))
            messages.success(request, 'تنظیمات با موفقیت ذخیره شد.')
            return redirect('admin_panel:site_settings')
        messages.error(request, 'لطفاً خطاهای فرم را برطرف کنید.')
        return render(request, self.template_name, {'form': form})


# ─── AI Assist ───────────────────────────────────────────────

class AdminAIAssistView(PanelPermissionMixin, View):
    permission_required = 'blog.add_blogpost'
    def post(self, request):
        prompt = request.POST.get('prompt', '').strip()
        style = request.POST.get('style', 'formal')
        if not prompt:
            return JsonResponse({'error': 'متن درخواست الزامی است.'}, status=400)

        style_map = {
            'formal': 'رسمی و حرفه‌ای',
            'informal': 'غیررسمی و صمیمی',
            'technical': 'فنی و تخصصی',
        }
        style_text = style_map.get(style, 'رسمی')

        try:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=2048,
                messages=[{
                    'role': 'user',
                    'content': (
                        f'لطفاً یک مقاله وبلاگ به فارسی با لحن {style_text} بنویسید.\n'
                        f'مقاله باید شامل عنوان، خلاصه کوتاه و محتوای کامل باشد.\n'
                        f'موضوع مقاله در حوزه ابزارآلات و مصالح ساختمانی است.\n\n'
                        f'موضوع: {prompt}'
                    ),
                }],
            )
            return JsonResponse({'content': message.content[0].text})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ─── Global Search ───────────────────────────────────────────

class AdminGlobalSearchView(StaffRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return JsonResponse({'results': []})

        results = []
        for p in Product.objects.filter(Q(name__icontains=q) | Q(barcode__icontains=q))[:5]:
            results.append({'type': 'محصول', 'title': p.name, 'url': f'/panel/products/{p.pk}/edit/'})
        for u in User.objects.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(mobile__icontains=q))[:5]:
            results.append({'type': 'کاربر', 'title': str(u), 'url': '/panel/users/'})
        for inv in Invoice.objects.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q))[:5]:
            results.append({'type': 'فاکتور', 'title': f'{inv.invoice_number} - {inv.customer_name}', 'url': f'/panel/invoices/{inv.pk}/'})
        for bp in BlogPost.objects.filter(title__icontains=q)[:5]:
            results.append({'type': 'مقاله', 'title': bp.title, 'url': f'/panel/posts/{bp.pk}/edit/'})

        return JsonResponse({'results': results})
