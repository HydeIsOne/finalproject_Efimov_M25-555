from __future__ import annotations

from abc import ABC, abstractmethod

from .exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Abstract base currency type.

    Public attributes:
      - name: str
      - code: str (2–5 uppercase, no spaces)
    """

    name: str
    code: str

    def __init__(self, name: str, code: str) -> None:
        c = (code or "").strip().upper()
        n = (name or "").strip()
        if not n:
            raise ValueError("name must be non-empty")
        if not (2 <= len(c) <= 5) or not c.isalnum() or " " in c:
            raise ValueError(
                "code must be 2–5 uppercase alnum characters without spaces"
            )
        self.name = n
        self.code = c

    @abstractmethod
    def get_display_info(self) -> str:  # pragma: no cover - formatting only
        ...


class FiatCurrency(Currency):
    issuing_country: str

    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name, code)
        self.issuing_country = (issuing_country or "").strip()
        if not self.issuing_country:
            raise ValueError("issuing_country must be non-empty")

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    algorithm: str
    market_cap: float

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        super().__init__(name, code)
        self.algorithm = (algorithm or "").strip()
        self.market_cap = float(market_cap or 0.0)
        if not self.algorithm:
            raise ValueError("algorithm must be non-empty")

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, "
            f"MCAP: {self.market_cap:.2e})"
        )


# Simple registry. In a real system this could be loaded from config/DB.
_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11),
}


def get_currency(code: str) -> Currency:
    c = (code or "").strip().upper()
    cur = _REGISTRY.get(c)
    if not cur:
        raise CurrencyNotFoundError(c)
    return cur


def list_supported() -> list[Currency]:
    """Return list of supported currencies (registry snapshot)."""
    return list(_REGISTRY.values())
