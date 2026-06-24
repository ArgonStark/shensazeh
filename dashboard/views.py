from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.views import View


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class DashboardView(StaffRequiredMixin, View):
    """Redirect old dashboard to the new admin panel."""

    def get(self, request):
        return redirect('admin_panel:dashboard')
