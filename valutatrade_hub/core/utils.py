"""Utility helpers for ValutaTrade Hub.

Валидации валютных кодов, нормализация и простые конвертации.
"""

from __future__ import annotations

from typing import Any

from . import currencies as cur
from .models import DomainError


def normalize_code(code: str) -> str:
    """Normalize currency code to uppercase trimmed string."""
    return (code or "").strip().upper()


def is_currency(code: str) -> bool:
    """Return True if code is a supported currency in registry."""
    try:
        cur.get_currency(normalize_code(code))
        return True
    except Exception:  # noqa: BLE001
        return False


def validate_currency_code(code: str) -> str:
    """Validate and return normalized currency code or raise error.

    Raises:
        CurrencyNotFoundError: if code is unknown
    """
    n = normalize_code(code)
    cur.get_currency(n)
    return n


def parse_amount(value: Any, *, positive: bool = True) -> float:
    """Parse amount to float with optional positivity constraint.

    Raises:
        DomainError: when parsing fails or constraint violated
    """
    try:
        amt = float(value)
    except (TypeError, ValueError) as exc:  # noqa: PERF203
        raise DomainError("'amount' должен быть числом") from exc
    if positive and amt <= 0:
        raise DomainError("'amount' должен быть положительным числом")
    return amt


def compute_value(amount: float, rate: float) -> float:
    """Return amount * rate (helper for conversions)."""
    return float(amount) * float(rate)


def format_money(value: float, decimals: int = 2, grouping: bool = True) -> str:
    """Format monetary value with fixed decimals and optional thousands sep."""
    fmt = f"{{:,.{decimals}f}}" if grouping else f"{{:.{decimals}f}}"
    return fmt.format(float(value))
