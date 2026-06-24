from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.AdminDashboardView.as_view(), name='dashboard'),
    # Products
    path('products/', views.AdminProductListView.as_view(), name='product_list'),
    path('products/create/', views.AdminProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/edit/', views.AdminProductEditView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.AdminProductDeleteView.as_view(), name='product_delete'),
    # Categories
    path('categories/', views.AdminCategoryListView.as_view(), name='category_list'),
    path('categories/create/', views.AdminCategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/edit/', views.AdminCategoryEditView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.AdminCategoryDeleteView.as_view(), name='category_delete'),
    # Reviews
    path('reviews/', views.AdminReviewListView.as_view(), name='review_list'),
    path('reviews/<int:pk>/approve/', views.AdminReviewApproveView.as_view(), name='review_approve'),
    path('reviews/<int:pk>/delete/', views.AdminReviewDeleteView.as_view(), name='review_delete'),
    # Inventory
    path('inventory/', views.AdminInventoryListView.as_view(), name='inventory_list'),
    path('inventory/create/', views.AdminInventoryCreateView.as_view(), name='inventory_create'),
    path('inventory/report/', views.AdminInventoryReportView.as_view(), name='inventory_report'),
    # Invoices
    path('invoices/', views.AdminInvoiceListView.as_view(), name='invoice_list'),
    path('invoices/create/', views.AdminInvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', views.AdminInvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.AdminInvoiceEditView.as_view(), name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.AdminInvoiceDeleteView.as_view(), name='invoice_delete'),
    path('invoices/<int:pk>/pdf/', views.AdminInvoicePDFView.as_view(), name='invoice_pdf'),
    # Blog
    path('posts/', views.AdminPostListView.as_view(), name='post_list'),
    path('posts/create/', views.AdminPostCreateView.as_view(), name='post_create'),
    path('posts/<int:pk>/edit/', views.AdminPostEditView.as_view(), name='post_edit'),
    path('posts/<int:pk>/delete/', views.AdminPostDeleteView.as_view(), name='post_delete'),
    path('posts/<int:pk>/toggle-publish/', views.AdminPostTogglePublishView.as_view(), name='post_toggle_publish'),
    # Announcements
    path('announcements/', views.AdminAnnouncementListView.as_view(), name='announcement_list'),
    path('announcements/create/', views.AdminAnnouncementCreateView.as_view(), name='announcement_create'),
    path('announcements/<int:pk>/edit/', views.AdminAnnouncementEditView.as_view(), name='announcement_edit'),
    path('announcements/<int:pk>/delete/', views.AdminAnnouncementDeleteView.as_view(), name='announcement_delete'),
    # Users
    path('users/', views.AdminUserListView.as_view(), name='user_list'),
    path('staff/', views.AdminStaffListView.as_view(), name='staff_list'),
    path('staff/create/', views.AdminStaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:pk>/delete/', views.AdminStaffDeleteView.as_view(), name='staff_delete'),
    # Services
    path('services/', views.AdminServiceListView.as_view(), name='service_list'),
    path('services/create/', views.AdminServiceCreateView.as_view(), name='service_create'),
    path('services/<int:pk>/edit/', views.AdminServiceEditView.as_view(), name='service_edit'),
    path('services/<int:pk>/delete/', views.AdminServiceDeleteView.as_view(), name='service_delete'),
    # Projects
    path('projects/', views.AdminProjectListView.as_view(), name='project_list'),
    path('projects/create/', views.AdminProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/edit/', views.AdminProjectEditView.as_view(), name='project_edit'),
    path('projects/<int:pk>/delete/', views.AdminProjectDeleteView.as_view(), name='project_delete'),
    # Settings
    path('settings/', views.AdminSiteSettingsView.as_view(), name='site_settings'),
    # API
    path('ai-assist/', views.AdminAIAssistView.as_view(), name='ai_assist'),
    path('search/', views.AdminGlobalSearchView.as_view(), name='global_search'),
]
