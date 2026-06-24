from django.contrib import admin

from .models import Category, Product, ProductImage, ProductReview


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    verbose_name = 'تصویر محصول'
    verbose_name_plural = 'تصاویر محصول'


class ProductReviewInline(admin.StackedInline):
    model = ProductReview
    extra = 0
    readonly_fields = ('created_at',)
    verbose_name = 'نظر'
    verbose_name_plural = 'نظرات'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'slug', 'order', 'is_active', 'created_at')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('order', 'is_active')
    ordering = ('order', 'name')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'barcode', 'is_active', 'created_at')
    list_filter = ('is_active', 'category', 'created_at')
    search_fields = ('name', 'slug', 'barcode', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'stock', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ProductImageInline, ProductReviewInline]
    raw_id_fields = ('category',)
    ordering = ('-created_at',)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'alt_text', 'is_primary', 'order')
    list_filter = ('is_primary',)
    search_fields = ('product__name', 'alt_text')
    raw_id_fields = ('product',)


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'rating', 'created_at')
    search_fields = ('product__name', 'user__mobile', 'user__first_name', 'text')
    raw_id_fields = ('product', 'user')
    readonly_fields = ('created_at',)
    actions = ['approve_reviews']

    @admin.action(description='تأیید نظرات انتخاب شده')
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
