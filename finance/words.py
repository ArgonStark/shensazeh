"""Number → Persian words, for cheque printing and official invoices."""

from num2fawords import words

from .money import rial_to_toman


def amount_to_words(amount: int, unit: str = 'ریال') -> str:
    """e.g. 1500000 -> 'یک میلیون و پانصد هزار ریال'."""
    amount = int(amount)
    if amount == 0:
        return f'صفر {unit}'
    sign = 'منفی ' if amount < 0 else ''
    return f'{sign}{words(abs(amount))} {unit}'


def rial_to_words(amount_rial: int) -> str:
    return amount_to_words(amount_rial, 'ریال')


def rial_to_toman_words(amount_rial: int) -> str:
    """Amount stored in Rial, spelled out in Toman."""
    return amount_to_words(rial_to_toman(amount_rial), 'تومان')
