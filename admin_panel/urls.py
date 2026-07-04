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
    path('products/<int:pk>/kardex/', views.AdminProductKardexView.as_view(), name='product_kardex'),
    path('products/export/', views.AdminProductExportView.as_view(), name='product_export'),
    path('products/import/', views.AdminProductImportView.as_view(), name='product_import'),
    # Invoices
    path('invoices/', views.AdminInvoiceListView.as_view(), name='invoice_list'),
    path('invoices/create/', views.AdminInvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/export/', views.AdminInvoiceExportView.as_view(), name='invoice_export'),
    path('invoices/<int:pk>/', views.AdminInvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.AdminInvoiceEditView.as_view(), name='invoice_edit'),
    path('invoices/<int:pk>/issue/', views.AdminInvoiceIssueView.as_view(), name='invoice_issue'),
    path('invoices/<int:pk>/cancel/', views.AdminInvoiceCancelView.as_view(), name='invoice_cancel'),
    path('invoices/<int:pk>/delete/', views.AdminInvoiceDeleteView.as_view(), name='invoice_delete'),
    path('invoices/<int:pk>/pdf/', views.AdminInvoicePDFView.as_view(), name='invoice_pdf'),
    # Installments
    path('installments/', views.AdminInstallmentListView.as_view(), name='installment_list'),
    path('installments/plan/<int:pk>/', views.AdminInstallmentPlanDetailView.as_view(), name='installment_plan_detail'),
    path('installments/create/<int:pk>/', views.AdminInstallmentPlanCreateView.as_view(), name='installment_plan_create'),
    path('installments/pay/<int:pk>/', views.AdminInstallmentPayView.as_view(), name='installment_pay'),
    # Cash flow
    path('cashflow/', views.AdminCashFlowView.as_view(), name='cashflow'),
    path('cashflow/create/', views.AdminCashTransactionCreateView.as_view(), name='cashflow_create'),
    path('cashflow/<int:pk>/delete/', views.AdminCashTransactionDeleteView.as_view(), name='cashflow_delete'),
    path('cashflow/categories/create/', views.AdminExpenseCategoryCreateView.as_view(), name='expense_category_create'),
    # Cheques
    path('cheques/', views.AdminChequeListView.as_view(), name='cheque_list'),
    path('cheques/create/', views.AdminChequeCreateView.as_view(), name='cheque_create'),
    path('cheques/due-report/', views.AdminChequeDueReportView.as_view(), name='cheque_due_report'),
    path('cheques/books/', views.AdminChequeBookListView.as_view(), name='chequebook_list'),
    path('cheques/books/create/', views.AdminChequeBookCreateView.as_view(), name='chequebook_create'),
    path('cheques/books/<int:pk>/toggle/', views.AdminChequeBookToggleView.as_view(), name='chequebook_toggle'),
    path('cheques/<int:pk>/edit/', views.AdminChequeEditView.as_view(), name='cheque_edit'),
    path('cheques/<int:pk>/status/', views.AdminChequeStatusView.as_view(), name='cheque_status'),
    path('cheques/<int:pk>/print/', views.AdminChequePrintView.as_view(), name='cheque_print'),
    path('cheques/<int:pk>/layout/', views.AdminChequeLayoutEditView.as_view(), name='cheque_layout'),
    # Parties
    path('parties/', views.AdminPartyListView.as_view(), name='party_list'),
    path('parties/create/', views.AdminPartyCreateView.as_view(), name='party_create'),
    path('parties/report/', views.AdminPartyBalanceReportView.as_view(), name='party_balance_report'),
    path('parties/report/pdf/', views.AdminPartyBalanceReportPDFView.as_view(), name='party_balance_report_pdf'),
    path('parties/export/', views.AdminPartyExportView.as_view(), name='party_export'),
    path('parties/import/', views.AdminPartyImportView.as_view(), name='party_import'),
    path('parties/<int:pk>/edit/', views.AdminPartyEditView.as_view(), name='party_edit'),
    path('parties/<int:pk>/ledger/', views.AdminPartyLedgerView.as_view(), name='party_ledger'),
    path('parties/<int:pk>/ledger/pdf/', views.AdminPartyLedgerPDFView.as_view(), name='party_ledger_pdf'),
    path('parties/<int:pk>/ledger/excel/', views.AdminPartyLedgerExportView.as_view(), name='party_ledger_excel'),
    path('parties/<int:pk>/payment/', views.AdminPaymentCreateView.as_view(), name='party_payment'),
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
    path('staff/<int:pk>/permissions/', views.AdminStaffPermissionsView.as_view(), name='staff_permissions'),
    # Audit
    path('audit/', views.AdminAuditLogListView.as_view(), name='audit_list'),
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
