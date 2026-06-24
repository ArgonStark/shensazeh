from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.InventoryListView.as_view(), name='inventory_list'),
    path('create/', views.InventoryCreateView.as_view(), name='inventory_create'),
    path('dashboard/', views.InventoryDashboardView.as_view(), name='inventory_dashboard'),
]
