from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import ListView

from .models import TelegramMessage


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )


class TelegramLogView(StaffRequiredMixin, ListView):
    """Staff only: list sent Telegram messages."""
    model = TelegramMessage
    template_name = 'telegram_bot/telegram_log.html'
    context_object_name = 'messages'
    paginate_by = 30

    def get_queryset(self):
        return TelegramMessage.objects.select_related('product').order_by('-created_at')
