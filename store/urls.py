from django.urls import path

from . import views

app_name = 'store'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('category/<slug:slug>/', views.CategoryDetailView.as_view(), name='category_detail'),
    path('product/<slug:slug>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('product/<slug:slug>/review/', views.ProductReviewCreateView.as_view(), name='product_review_create'),
]
