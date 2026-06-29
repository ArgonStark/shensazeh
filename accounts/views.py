from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, UpdateView

from .models import User, OTPCode, StaffProfile
from .sms_service import send_otp, generate_otp_code


class LoginView(View):
    """Email + password login. (SMS/OTP login will be added later.)"""
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('store:home')
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        if not email or not password:
            return render(request, self.template_name, {
                'error': 'ایمیل و رمز عبور را وارد کنید.',
                'email': email,
            })

        user = authenticate(request, email=email, password=password)
        if user is None:
            return render(request, self.template_name, {
                'error': 'ایمیل یا رمز عبور نادرست است.',
                'email': email,
            })

        login(request, user)
        next_url = request.POST.get('next') or request.GET.get('next')
        return redirect(next_url or 'store:home')


class VerifyOTPView(View):
    """Verify the OTP code and login or create the user."""
    template_name = 'accounts/verify_otp.html'

    def get(self, request):
        mobile = request.session.get('otp_mobile')
        if not mobile:
            return redirect('accounts:login')
        return render(request, self.template_name, {'mobile': mobile})

    def post(self, request):
        mobile = request.session.get('otp_mobile')
        if not mobile:
            return redirect('accounts:login')

        code = request.POST.get('code', '').strip()
        otp = OTPCode.objects.filter(
            mobile=mobile,
            code=code,
            is_used=False,
        ).order_by('-created_at').first()

        if not otp:
            return render(request, self.template_name, {
                'mobile': mobile,
                'error': 'کد تأیید نامعتبر است.',
            })

        # Check expiry (2 minutes)
        age = (timezone.now() - otp.created_at).total_seconds()
        if age > 120:
            return render(request, self.template_name, {
                'mobile': mobile,
                'error': 'کد تأیید منقضی شده است.',
            })

        otp.is_used = True
        otp.save(update_fields=['is_used'])

        user, created = User.objects.get_or_create(
            mobile=mobile,
            defaults={'username': mobile},
        )
        login(request, user)
        del request.session['otp_mobile']

        if created or not user.first_name:
            return redirect('accounts:complete_profile')
        return redirect('store:home')


class ProfileView(LoginRequiredMixin, UpdateView):
    """Show and edit user profile."""
    model = User
    template_name = 'accounts/profile.html'
    fields = ['first_name', 'last_name', 'province', 'city', 'address', 'postal_code']
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user


class CompleteProfileView(LoginRequiredMixin, UpdateView):
    """After first login, fill in name/address/etc."""
    model = User
    template_name = 'accounts/complete_profile.html'
    fields = ['first_name', 'last_name', 'province', 'city', 'address', 'postal_code']
    success_url = reverse_lazy('store:home')

    def get_object(self, queryset=None):
        return self.request.user


class LogoutView(View):
    """Log the user out and redirect to home."""

    def get(self, request):
        logout(request)
        return redirect('store:home')

    def post(self, request):
        logout(request)
        return redirect('store:home')


class StaffRequiredMixin(UserPassesTestMixin):
    """Mixin that requires the user to be a superuser or active staff."""

    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class StaffListView(StaffRequiredMixin, ListView):
    """Admin only: list staff members."""
    model = StaffProfile
    template_name = 'accounts/staff_list.html'
    context_object_name = 'staff_members'
    paginate_by = 20

    def get_queryset(self):
        return StaffProfile.objects.select_related('user').filter(is_active_staff=True)


class StaffCreateView(StaffRequiredMixin, View):
    """Admin only: add a staff member."""
    template_name = 'accounts/staff_create.html'

    def get(self, request):
        return render(request, self.template_name, {
            'role_choices': StaffProfile.ROLE_CHOICES,
        })

    def post(self, request):
        mobile = request.POST.get('mobile', '').strip()
        role = request.POST.get('role', '').strip()

        if not mobile or not role:
            return render(request, self.template_name, {
                'error': 'تمام فیلدها الزامی هستند.',
                'role_choices': StaffProfile.ROLE_CHOICES,
            })

        user, _ = User.objects.get_or_create(
            mobile=mobile,
            defaults={'username': mobile},
        )
        user.is_staff = True
        user.save(update_fields=['is_staff'])

        StaffProfile.objects.update_or_create(
            user=user,
            defaults={'role': role, 'is_active_staff': True},
        )
        return redirect('accounts:staff_list')
