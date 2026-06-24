from .models import Category


def categories_processor(request):
    """Return all active root categories for use in templates."""
    categories = Category.objects.filter(
        is_active=True,
        parent__isnull=True,
    ).prefetch_related('children')
    return {'root_categories': categories}
