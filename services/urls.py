from django.urls import path

from . import views

app_name = 'services'

urlpatterns = [
    path('', views.ServiceListView.as_view(), name='service_list'),
    path('service/<slug:slug>/', views.ServiceDetailView.as_view(), name='service_detail'),
    path('projects/', views.ProjectListView.as_view(), name='project_list'),
    path('projects/<slug:slug>/', views.ProjectDetailView.as_view(), name='project_detail'),
]
