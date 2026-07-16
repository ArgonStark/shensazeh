from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, register_converter

from store.views import HomeView, ProductSearchAPIView
from .converters import UnicodeSlugConverter

register_converter(UnicodeSlugConverter, 'uslug')

urlpatterns = [
    path('admin/', admin.site.urls),

    # Home
    path('', HomeView.as_view(), name='home'),

    # App URLs
    path('accounts/', include('accounts.urls')),
    path('store/', include('store.urls')),
    path('inventory/', include('inventory.urls')),
    path('orders/', include('orders.urls')),
    path('blog/', include('blog.urls')),
    path('services/', include('services.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('telegram/', include('telegram_bot.urls')),
    path('panel/', include('admin_panel.urls')),

    # DRF API
    path('api/products/search/', ProductSearchAPIView.as_view(), name='api-product-search'),
    path('api/auth/', include('rest_framework.urls')),
]

# Serve media in DEBUG; in production nginx serves /media/.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
