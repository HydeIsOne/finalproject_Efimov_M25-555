"""Domain models for ValutaTrade Hub.

Note: Implementation will be added in subsequent steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


class DomainError(Exception):
    """Base exception for domain-specific errors."""


@dataclass(slots=True)
class User:
    user_id: str
    username: str
    # password storage TBD (hashed)


@dataclass(slots=True)
class Portfolio:
    user_id: str
    base_currency: str = "USD"
    balances: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Trade:
    user_id: str
    symbol: str  # e.g., "BTC", "EUR"
    side: str  # "buy" or "sell"
    qty: float
    price: float
    timestamp: float


@dataclass(slots=True)
class Rate:
    symbol: str
    price: float
    ts: float
