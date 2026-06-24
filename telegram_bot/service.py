import logging

from django.conf import settings
from telegram import Bot

from .models import TelegramMessage

logger = logging.getLogger(__name__)


def send_product_notification(product):
    """Send a product notification message to the Telegram channel.

    Args:
        product: A store.Product instance.

    Returns:
        TelegramMessage instance.
    """
    message_text = (
        f"محصول جدید: {product.name}\n"
        f"قیمت: {product.price:,} ریال\n"
        f"دسته‌بندی: {product.category.name}\n"
    )
    if product.description:
        message_text += f"\n{product.description[:200]}"

    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    message_text += f"\n\nمشاهده محصول: {site_url}/store/product/{product.slug}/"

    telegram_msg = TelegramMessage(
        product=product,
        message_text=message_text,
    )

    try:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        result = bot.send_message(
            chat_id=settings.TELEGRAM_CHANNEL_ID,
            text=message_text,
        )
        telegram_msg.message_id = str(result.message_id)
        telegram_msg.is_sent = True
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        telegram_msg.error_message = str(e)
        telegram_msg.is_sent = False

    telegram_msg.save()
    return telegram_msg
