import abc
import logging
import random

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


def generate_otp_code() -> str:
    """Generate a 6-digit OTP code."""
    return str(random.randint(100000, 999999))


def get_sms_provider() -> SMSProvider:
    """Return the configured SMS provider instance."""
    return ConsoleSMSProvider()


def send_otp(mobile: str, code: str) -> bool:
    """Send an OTP code to the given mobile number."""
    provider = get_sms_provider()
    message = f"کد تأیید شما: {code}"
    return provider.send(mobile, message)
