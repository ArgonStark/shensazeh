from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Sum, Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, TemplateView

from store.models import Product
from .models import InventoryEntry


class StaffRequiredMixin(UserPassesTestMixin):
    """Require the user to be staff or superuser."""

    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class InventoryListView(StaffRequiredMixin, ListView):
    """List all inventory entries (staff only)."""
    model = InventoryEntry
    template_name = 'inventory/inventory_list.html'
    context_object_name = 'entries'
    paginate_by = 30

    def get_queryset(self):
        queryset = InventoryEntry.objects.select_related('product', 'created_by', 'order')
        entry_type = self.request.GET.get('type')
        if entry_type in ('in', 'out'):
            queryset = queryset.filter(entry_type=entry_type)
        return queryset


class InventoryCreateView(StaffRequiredMixin, CreateView):
    """Add a new inventory entry (staff only)."""
    model = InventoryEntry
    template_name = 'inventory/inventory_create.html'
    fields = ['product', 'entry_type', 'quantity', 'supplier', 'reference', 'notes']
    success_url = reverse_lazy('inventory:inventory_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class InventoryDashboardView(StaffRequiredMixin, TemplateView):
    """Overview of stock levels (staff only)."""
    template_name = 'inventory/inventory_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        products = Product.objects.filter(is_active=True)
        context['total_products'] = products.count()
        context['out_of_stock'] = products.filter(stock=0).count()
        context['low_stock'] = products.filter(stock__gt=0, stock__lte=10).count()
        context['products'] = products.order_by('stock')[:20]

        context['total_in'] = (
            InventoryEntry.objects
            .filter(entry_type='in')
            .aggregate(total=Sum('quantity'))['total'] or 0
        )
        context['total_out'] = (
            InventoryEntry.objects
            .filter(entry_type='out')
            .aggregate(total=Sum('quantity'))['total'] or 0
        )
        context['recent_entries'] = InventoryEntry.objects.select_related('product')[:10]

        return context
