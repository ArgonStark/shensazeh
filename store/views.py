from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, ListView, DetailView, CreateView
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from blog.models import BlogPost, Announcement
from services.models import Service
from .models import Category, Product, ProductReview
from .serializers import ProductSerializer


class HomeView(TemplateView):
    """Landing page with featured products, categories, services and news."""
    template_name = 'store/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['featured_products'] = (
            Product.objects
            .filter(is_active=True)
            .select_related('category')
            .prefetch_related('images')[:8]
        )
        context['featured_categories'] = (
            Category.objects
            .filter(is_active=True, parent__isnull=True)
            .annotate(product_count=Count('products', filter=Q(products__is_active=True)))
            [:8]
        )
        context['services'] = Service.objects.filter(is_active=True)[:6]
        context['announcements'] = Announcement.objects.filter(is_active=True)[:4]
        context['latest_posts'] = (
            BlogPost.objects.filter(is_published=True).select_related('author')[:3]
        )
        context['total_products'] = Product.objects.filter(is_active=True).count()
        return context


class CategoryListView(ListView):
    """All active categories."""
    model = Category
    template_name = 'store/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        return Category.objects.filter(is_active=True, parent__isnull=True)


class CategoryDetailView(DetailView):
    """Products in a category (by slug)."""
    model = Category
    template_name = 'store/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'

    def get_queryset(self):
        return Category.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object
        # Include products from this category and its children
        descendant_ids = [category.pk] + list(
            category.children.filter(is_active=True).values_list('pk', flat=True)
        )
        context['products'] = (
            Product.objects
            .filter(category_id__in=descendant_ids, is_active=True)
            .select_related('category')
            .prefetch_related('images')
        )
        return context


class ProductDetailView(DetailView):
    """Single product with images and reviews."""
    model = Product
    template_name = 'store/product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'

    def get_queryset(self):
        return (
            Product.objects
            .filter(is_active=True)
            .select_related('category')
            .prefetch_related('images', 'reviews__user')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reviews'] = self.object.reviews.filter(is_approved=True).select_related('user')
        context['product_images'] = self.object.images.all()
        # specifications JSONField -> list of {key, value} for the spec table
        specs = self.object.specifications or {}
        context['specs'] = [{'key': k, 'value': v} for k, v in specs.items()]
        # Related products from the same category
        context['related_products'] = (
            Product.objects
            .filter(category=self.object.category, is_active=True)
            .exclude(pk=self.object.pk)
            .prefetch_related('images')[:4]
        )
        return context


class ProductReviewCreateView(LoginRequiredMixin, CreateView):
    """POST to add a review for a product."""
    model = ProductReview
    fields = ['rating', 'text']
    template_name = 'store/review_form.html'

    def form_valid(self, form):
        product = get_object_or_404(Product, slug=self.kwargs['slug'], is_active=True)
        form.instance.user = self.request.user
        form.instance.product = product
        form.save()
        return redirect(reverse('store:product_detail', kwargs={'slug': product.slug}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['product'] = get_object_or_404(
            Product, slug=self.kwargs['slug'], is_active=True
        )
        return context


# ----- DRF API Views -----

class ProductSearchAPIView(ListAPIView):
    """API endpoint for product search."""
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).select_related('category')
        query = self.request.query_params.get('q', '').strip()
        category_slug = self.request.query_params.get('category', '').strip()

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(barcode__icontains=query)
            )
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        return queryset
