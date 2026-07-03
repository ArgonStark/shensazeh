"""Money helpers.

Rule of the codebase: every amount is stored as an integer in **Rial**.
Toman exists only at the display edge (1 Toman = 10 Rial). Never use floats.
"""

RIALS_PER_TOMAN = 10


def rial_to_toman(rial: int) -> int:
    """Convert Rial to Toman, truncating toward zero (sub-Toman Rials drop)."""
    rial = int(rial)
    sign = -1 if rial < 0 else 1
    return sign * (abs(rial) // RIALS_PER_TOMAN)


def toman_to_rial(toman: int) -> int:
    return int(toman) * RIALS_PER_TOMAN


def format_amount(value: int) -> str:
    """Group digits with commas: 1500000 -> '1,500,000'."""
    return f'{int(value):,}'


def percent_of(amount: int, rate_percent: int) -> int:
    """Integer percentage with floor rounding — the single VAT rounding rule.

    e.g. percent_of(1_000_005, 10) == 100_000 (sub-Rial fractions drop).
    """
    return (int(amount) * int(rate_percent)) // 100
