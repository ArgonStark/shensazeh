import abc
import json
import logging
import random
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


class SMSProvider(abc.ABC):
    """Abstract base class for SMS providers."""

    @abc.abstractmethod
    def send(self, mobile: str, message: str) -> bool:
        """Send an SMS message. Returns True on success."""
        raise NotImplementedError


class ConsoleSMSProvider(SMSProvider):
    """SMS provider that prints to console (for development)."""

    def send(self, mobile: str, message: str) -> bool:
        logger.info("SMS to %s: %s", mobile, message)
        print(f"[SMS -> {mobile}] {message}")
        return True


class KavenegarSMSProvider(SMSProvider):
    """Kavenegar REST driver (https://kavenegar.com/rest.html).

    Credentials come from settings/env (SMS_API_KEY, SMS_SENDER) — never
    hardcoded. Failures are logged and reported as False, never raised.
    """

    def send(self, mobile: str, message: str) -> bool:
        if not settings.SMS_API_KEY:
            logger.error('Kavenegar selected but SMS_API_KEY is empty')
            return False
        url = f'https://api.kavenegar.com/v1/{settings.SMS_API_KEY}/sms/send.json'
        data = urllib.parse.urlencode({
            'receptor': mobile,
            'message': message,
            **({'sender': settings.SMS_SENDER} if settings.SMS_SENDER else {}),
        }).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as response:
                payload = json.load(response)
            ok = payload.get('return', {}).get('status') == 200
            if not ok:
                logger.error('Kavenegar rejected SMS to %s: %s', mobile, payload)
            return ok
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.error('Kavenegar send failed for %s: %s', mobile, exc)
            return False


PROVIDERS = {
    'console': ConsoleSMSProvider,
    'kavenegar': KavenegarSMSProvider,
}


def generate_otp_code() -> str:
    """Generate a 6-digit OTP code."""
    return str(random.randint(100000, 999999))


def get_sms_provider() -> SMSProvider:
    """Return the provider selected by SMS_PROVIDER (env), console by default."""
    key = getattr(settings, 'SMS_PROVIDER', 'console')
    return PROVIDERS.get(key, ConsoleSMSProvider)()


def send_otp(mobile: str, code: str) -> bool:
    """Send an OTP code to the given mobile number."""
    provider = get_sms_provider()
    message = f"کد تأیید شما: {code}"
    return provider.send(mobile, message)
