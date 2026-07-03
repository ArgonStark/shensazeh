from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from admin_panel.views import PanelPermissionMixin

from .models import Order, OrderItem, Invoice, InvoiceItem


class StaffRequiredMixin(UserPassesTestMixin):
    """Require the user to be staff or superuser."""

    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


# ----- Order Views -----

class OrderListView(LoginRequiredMixin, ListView):
    """List the current user's orders."""
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user)


class OrderDetailView(LoginRequiredMixin, DetailView):
    """Single order detail."""
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        qs = Order.objects.prefetch_related('items__product')
        if not self.request.user.is_staff:
            qs = qs.filter(customer=self.request.user)
        return qs


class OrderCreateView(LoginRequiredMixin, View):
    """Create an order from cart data (POST)."""
    template_name = 'orders/order_create.html'

    def get(self, request):
        from django.shortcuts import render
        return render(request, self.template_name)

    def post(self, request):
        from django.shortcuts import render, redirect
        from store.models import Product

        items_data = []
        # Expect POST data with items as product_id and quantity pairs
        product_ids = request.POST.getlist('product_id')
        quantities = request.POST.getlist('quantity')

        if not product_ids:
            return render(request, self.template_name, {
                'error': 'سبد خرید خالی است.',
            })

        order = Order.objects.create(customer=request.user)
        total = 0

        for pid, qty in zip(product_ids, quantities):
            try:
                product = Product.objects.get(pk=pid, is_active=True)
                quantity = max(1, int(qty))
            except (Product.DoesNotExist, ValueError):
                continue

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
            )
            total += product.price * quantity

        order.total_amount = total
        order.save(update_fields=['total_amount'])
        return redirect('orders:order_detail', pk=order.pk)


# ----- Invoice Views -----

class InvoiceListView(PanelPermissionMixin, ListView):
    """Staff only: list invoices."""
    permission_required = 'orders.view_invoice'
    model = Invoice
    template_name = 'orders/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        return Invoice.objects.select_related('order__customer')


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    """Single invoice: staff with view permission, or the owning customer."""
    model = Invoice
    template_name = 'orders/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        qs = Invoice.objects.select_related('order__customer').prefetch_related('items__product')
        if self.request.user.has_perm('orders.view_invoice'):
            return qs
        return qs.filter(order__customer=self.request.user)


class InvoicePDFView(PanelPermissionMixin, View):
    """Generate a PDF of an invoice using WeasyPrint."""
    permission_required = 'orders.view_invoice'

    def get(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related('order__customer').prefetch_related('items__product'),
            pk=pk,
        )
        html_string = render_to_string('orders/invoice_pdf.html', {
            'invoice': invoice,
        })

        from weasyprint import HTML
        pdf_file = HTML(string=html_string).write_pdf()

        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="invoice-{invoice.invoice_number}.pdf"'
        )
        return response
