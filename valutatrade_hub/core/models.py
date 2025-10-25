"""Domain models for ValutaTrade Hub.

This module defines basic OOP entities: User, Wallet, Portfolio.
Other entities (Trade, Rate) will be implemented later.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


class DomainError(Exception):
    """Base exception for domain-specific errors."""


class User:
    """System user.

    Attributes are private by convention and exposed via properties.
    Passwords are stored as one-way hashes with a per-user salt.
    """

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        if not isinstance(user_id, int) or user_id < 0:
            raise DomainError("user_id must be a non-negative int")
        if not isinstance(username, str) or not username.strip():
            raise DomainError("username cannot be empty")
        if not isinstance(hashed_password, str) or not hashed_password:
            raise DomainError("hashed_password must be a non-empty string")
        if not isinstance(salt, str) or not salt:
            raise DomainError("salt must be a non-empty string")
        if not isinstance(registration_date, datetime):
            raise DomainError("registration_date must be a datetime")

        self._user_id = user_id
        self._username = username.strip()
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    # Properties (getters/setters)
    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise DomainError("username cannot be empty")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    # Behaviors
    def get_user_info(self) -> dict[str, str | int]:
        """Return safe user info without password hash."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def _hash(self, password: str) -> str:
        # Simplified one-way hash as per assignment
        blob = (password + self._salt).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def change_password(self, new_password: str) -> None:
        if not isinstance(new_password, str):
            raise DomainError("password must be a string")
        if len(new_password) < 4:
            raise DomainError("password must be at least 4 characters long")
        self._hashed_password = self._hash(new_password)

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False
        return self._hash(password) == self._hashed_password


class Wallet:
    """User wallet for a single currency."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise DomainError("currency_code cannot be empty")
        self._currency_code = currency_code.strip().upper()
        self._balance = 0.0
        self.balance = balance  # validate via setter

    @property
    def currency_code(self) -> str:
        return self._currency_code

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if not isinstance(value, (int, float)):
            raise DomainError("balance must be a number")
        if value < 0:
            raise DomainError("balance cannot be negative")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        if not isinstance(amount, (int, float)):
            raise DomainError("amount must be a number")
        if amount <= 0:
            raise DomainError("amount must be positive")
        self._balance += float(amount)

    def withdraw(self, amount: float) -> None:
        if not isinstance(amount, (int, float)):
            raise DomainError("amount must be a number")
        if amount <= 0:
            raise DomainError("amount must be positive")
        if float(amount) > self._balance:
            # Defer to use-cases for rich error, keep generic here
            raise DomainError("insufficient funds")
        self._balance -= float(amount)

    def get_balance_info(self) -> dict[str, float | str]:
        return {"currency_code": self._currency_code, "balance": self._balance}


class Portfolio:
    """Collection of wallets for a single user."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        if not isinstance(user_id, int) or user_id < 0:
            raise DomainError("user_id must be a non-negative int")
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = dict(wallets or {})
        self._user = user  # optional reference; not serialized by default

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User:
        if self._user is None:
            raise DomainError("user object is not attached to this portfolio")
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        # Return a shallow copy to prevent external mutation
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        code = (currency_code or "").strip().upper()
        if not code:
            raise DomainError("currency_code cannot be empty")
        if code in self._wallets:
            raise DomainError("currency already exists in portfolio")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet:
        code = (currency_code or "").strip().upper()
        try:
            return self._wallets[code]
        except KeyError as exc:
            raise DomainError("wallet not found") from exc

    def get_total_value(self, base_currency: str = "USD") -> float:
        """Return total converted into base currency using fixed rates.

        For simplicity we maintain static rates to USD and derive other bases.
        """
        base = (base_currency or "USD").strip().upper()
        rates_to_usd: dict[str, float] = {
            "USD": 1.0,
            "EUR": 1.10,
            "BTC": 65000.0,
            "ETH": 3000.0,
            "RUB": 0.011,
        }
        if base not in rates_to_usd:
            raise DomainError("unknown base currency")

        # Convert each wallet balance to USD, then to base
        total_usd = 0.0
        for code, wallet in self._wallets.items():
            rate = rates_to_usd.get(code)
            if rate is None:
                # Skip unknown currencies instead of failing
                continue
            total_usd += wallet.balance * rate

        # Now convert USD total to base
        base_rate = rates_to_usd[base]
        if base == "USD":
            return round(total_usd, 8)
        # USD -> base: divide by base's USD price
        return round(total_usd / base_rate, 8)


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
