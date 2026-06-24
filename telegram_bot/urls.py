from django.urls import path

from . import views

app_name = 'telegram_bot'

urlpatterns = [
    path('log/', views.TelegramLogView.as_view(), name='telegram_log'),
]
