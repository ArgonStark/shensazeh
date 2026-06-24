from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('verify-otp/', views.VerifyOTPView.as_view(), name='verify_otp'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('complete-profile/', views.CompleteProfileView.as_view(), name='complete_profile'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('staff/', views.StaffListView.as_view(), name='staff_list'),
    path('staff/create/', views.StaffCreateView.as_view(), name='staff_create'),
]
