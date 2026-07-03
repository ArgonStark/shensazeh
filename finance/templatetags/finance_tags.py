from django import template

from finance import money, words

register = template.Library()

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


@register.filter
def toman(value):
    """Rial amount → formatted Toman number: 1500000 → '150,000'."""
    try:
        return money.format_amount(money.rial_to_toman(value))
    except (TypeError, ValueError):
        return value


@register.filter
def rial(value):
    """Rial amount → formatted Rial number: 1500000 → '1,500,000'."""
    try:
        return money.format_amount(int(value))
    except (TypeError, ValueError):
        return value


@register.filter
def rial_words(value):
    """Rial amount → Persian words: 1500000 → 'یک میلیون و پانصد هزار ریال'."""
    try:
        return words.rial_to_words(value)
    except (TypeError, ValueError):
        return value


@register.filter
def toman_words(value):
    """Rial amount → Persian words in Toman."""
    try:
        return words.rial_to_toman_words(value)
    except (TypeError, ValueError):
        return value


@register.filter
def fa_digits(value):
    """Convert Western digits in a string/number to Persian digits."""
    return str(value).translate(_FA_DIGITS)
