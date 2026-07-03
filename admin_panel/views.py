import json
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
from orders.models import Order, OrderItem, Invoice, InvoiceItem
from services.models import Service, Project, ProjectImage
from store.models import Category, Product, ProductImage, ProductReview

from parties.models import LedgerEntry, Party, PartyTag, Payment
from parties.services import LedgerError, ledger_rows_with_balance, record_payment

from . import permissions as panel_permissions
from .forms import (
    ProductForm, CategoryForm, InventoryEntryForm, InvoiceForm,
    BlogPostForm, AnnouncementForm, PartyForm, PaymentForm,
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
        ctx = super().get_context_data(**kwargs)
        ctx['total_sales'] = Order.objects.exclude(status='cancelled').aggregate(t=Sum('total_amount'))['t'] or 0
        ctx['order_count'] = Order.objects.exclude(status='cancelled').count()
        ctx['total_products'] = Product.objects.filter(is_active=True).count()
        ctx['user_count'] = User.objects.count()
        ctx['out_of_stock'] = Product.objects.filter(is_active=True, stock=0).count()
        ctx['low_stock_products'] = Product.objects.filter(is_active=True, stock__gt=0, stock__lte=10).order_by('stock')[:10]
        ctx['recent_invoices'] = Invoice.objects.select_related('order__customer').order_by('-created_at')[:5]
        ctx['invoice_count'] = Invoice.objects.count()
        ctx['announcements'] = Announcement.objects.filter(is_active=True)[:5]

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

        # Chart data
        from datetime import timedelta
        sales_labels, sales_values = [], []
        for i in range(29, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            total = Order.objects.filter(created_at__gte=day_start, created_at__lt=day_end).exclude(status='cancelled').aggregate(t=Sum('total_amount'))['t'] or 0
            import jdatetime
            jd = jdatetime.datetime.fromgregorian(datetime=day)
            sales_labels.append(f'{jd.month}/{jd.day}')
            sales_values.append(int(total))
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
            qs = qs.filter(stock__gt=10)
        elif stock == 'out_of_stock':
            qs = qs.filter(stock=0)
        elif stock == 'low_stock':
            qs = qs.filter(stock__gt=0, stock__lte=10)
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
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_action(self.request.user, 'create', form.instance)
        if form.instance.entry_type == 'in':
            try:
                from telegram_bot.service import send_product_notification
                send_product_notification(form.instance.product)
            except Exception:
                pass
        return response


class AdminInventoryReportView(PanelPermissionMixin, TemplateView):
    permission_required = 'inventory.view_inventoryentry'
    template_name = 'admin_panel/inventory/inventory_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        products = Product.objects.filter(is_active=True).select_related('category').order_by('stock')
        ctx['products'] = products
        ctx['total_products'] = products.count()
        ctx['out_of_stock'] = products.filter(stock=0).count()
        ctx['low_stock'] = products.filter(stock__gt=0, stock__lte=10).count()
        return ctx


# ─── Invoices ────────────────────────────────────────────────

class AdminInvoiceListView(PanelPermissionMixin, ListView):
    permission_required = 'orders.view_invoice'
    template_name = 'admin_panel/invoices/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        qs = Invoice.objects.select_related('order__customer').order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        paid = self.request.GET.get('paid', '').strip()
        if q:
            qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q))
        if paid == 'yes':
            qs = qs.filter(is_paid=True)
        elif paid == 'no':
            qs = qs.filter(is_paid=False)
        return qs


class AdminInvoiceCreateView(PanelPermissionMixin, View):
    permission_required = 'orders.add_invoice'
    template_name = 'admin_panel/invoices/invoice_form.html'

    def get(self, request):
        return self._render(request)

    @transaction.atomic
    def post(self, request):
        customer_name = request.POST.get('customer_name', '').strip()
        customer_mobile = request.POST.get('customer_mobile', '').strip()
        customer_address = request.POST.get('customer_address', '').strip()
        discount = int(request.POST.get('discount') or 0)
        tax = int(request.POST.get('tax') or 0)
        notes = request.POST.get('notes', '')

        product_ids = request.POST.getlist('product_id')
        descriptions = request.POST.getlist('description')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')

        if not customer_name or not product_ids:
            return self._render(request, error='نام مشتری و حداقل یک آیتم الزامی است.')

        # Create backing order
        customer, _ = User.objects.get_or_create(mobile=customer_mobile or '0000000000', defaults={'username': customer_mobile or 'walk-in'})
        order = Order.objects.create(customer=customer, status='confirmed')

        subtotal = 0
        for pid, desc, qty, price in zip(product_ids, descriptions, quantities, unit_prices):
            try:
                product = Product.objects.get(pk=int(pid))
                q = max(1, int(qty))
                p = max(0, int(price))
            except (Product.DoesNotExist, ValueError):
                continue
            OrderItem.objects.create(order=order, product=product, quantity=q, unit_price=p)
            subtotal += q * p

        order.total_amount = subtotal
        order.save(update_fields=['total_amount'])

        invoice = Invoice.objects.create(
            order=order,
            customer_name=customer_name,
            customer_mobile=customer_mobile,
            customer_address=customer_address,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            total=subtotal - discount + tax,
            notes=notes,
        )

        for pid, desc, qty, price in zip(product_ids, descriptions, quantities, unit_prices):
            try:
                product = Product.objects.get(pk=int(pid))
                q = max(1, int(qty))
                p = max(0, int(price))
            except (Product.DoesNotExist, ValueError):
                continue
            InvoiceItem.objects.create(invoice=invoice, product=product, description=desc, quantity=q, unit_price=p)

        log_action(request.user, 'create', invoice)
        return redirect('admin_panel:invoice_detail', pk=invoice.pk)

    def _render(self, request, error=None):
        from django.shortcuts import render
        products = Product.objects.filter(is_active=True).order_by('name')
        return render(request, self.template_name, {
            'products': products,
            'error': error,
            'page_title': 'فاکتور جدید',
        })


class AdminInvoiceDetailView(PanelPermissionMixin, DetailView):
    permission_required = 'orders.view_invoice'
    model = Invoice
    template_name = 'admin_panel/invoices/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.select_related('order__customer').prefetch_related('items__product')


class AdminInvoiceEditView(PanelPermissionMixin, View):
    permission_required = 'orders.change_invoice'
    template_name = 'admin_panel/invoices/invoice_form.html'

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice.objects.prefetch_related('items__product'), pk=pk)
        products = Product.objects.filter(is_active=True).order_by('name')
        from django.shortcuts import render
        return render(request, self.template_name, {
            'invoice': invoice,
            'products': products,
            'page_title': f'ویرایش فاکتور {invoice.invoice_number}',
            'edit_mode': True,
        })

    @transaction.atomic
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        before = model_snapshot(invoice)
        invoice.customer_name = request.POST.get('customer_name', '')
        invoice.customer_mobile = request.POST.get('customer_mobile', '')
        invoice.customer_address = request.POST.get('customer_address', '')
        invoice.discount = int(request.POST.get('discount') or 0)
        invoice.tax = int(request.POST.get('tax') or 0)
        invoice.notes = request.POST.get('notes', '')
        invoice.is_paid = 'is_paid' in request.POST

        invoice.items.all().delete()

        product_ids = request.POST.getlist('product_id')
        descriptions = request.POST.getlist('description')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')

        subtotal = 0
        for pid, desc, qty, price in zip(product_ids, descriptions, quantities, unit_prices):
            try:
                product = Product.objects.get(pk=int(pid))
                q = max(1, int(qty))
                p = max(0, int(price))
            except (Product.DoesNotExist, ValueError):
                continue
            InvoiceItem.objects.create(invoice=invoice, product=product, description=desc, quantity=q, unit_price=p)
            subtotal += q * p

        invoice.subtotal = subtotal
        invoice.total = subtotal - invoice.discount + invoice.tax
        invoice.save()
        log_action(request.user, 'update', invoice, before=before, after=model_snapshot(invoice))
        return redirect('admin_panel:invoice_detail', pk=invoice.pk)


class AdminInvoiceDeleteView(PanelPermissionMixin, View):
    permission_required = 'orders.delete_invoice'
    @transaction.atomic
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        log_action(request.user, 'delete', invoice, before=model_snapshot(invoice))
        invoice.delete()
        return redirect('admin_panel:invoice_list')


class AdminInvoicePDFView(PanelPermissionMixin, View):
    permission_required = 'orders.view_invoice'
    def get(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related('order__customer').prefetch_related('items__product'), pk=pk
        )
        html = render_to_string('orders/invoice_pdf.html', {'invoice': invoice})
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice-{invoice.invoice_number}.pdf"'
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
        qs = Party.objects.prefetch_related('tags').annotate(balance_amount=_party_balance_annotation())
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
