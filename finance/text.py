"""Normalization for user-typed numbers and Jalali dates (Persian digits etc.)."""

import jdatetime

_EN = '0123456789'
_FA = '۰۱۲۳۴۵۶۷۸۹'
_AR = '٠١٢٣٤٥٦٧٨٩'
_TO_EN = str.maketrans(_FA + _AR, _EN + _EN)


def normalize_digits(value: str) -> str:
    return str(value).translate(_TO_EN)


def parse_int(value, default=0) -> int:
    """Parse ints typed with Persian digits, commas or spaces. Negative rejected."""
    if value is None:
        return default
    cleaned = normalize_digits(value).replace(',', '').replace('٬', '').strip()
    if not cleaned:
        return default
    try:
        number = int(cleaned)
    except ValueError:
        return default
    return number if number >= 0 else default


def parse_jalali_date(value):
    """'1404/05/12' (any digit script) → jdatetime.date, or None."""
    cleaned = normalize_digits(value or '').strip().replace('-', '/')
    if not cleaned:
        return None
    try:
        return jdatetime.datetime.strptime(cleaned, '%Y/%m/%d').date()
    except ValueError:
        return None
