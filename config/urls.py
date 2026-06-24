from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from store.views import HomeView, ProductSearchAPIView

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

import os
# Serve media in DEBUG, or on Vercel (read-only demo) where there's no nginx.
if settings.DEBUG or os.environ.get('VERCEL'):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
