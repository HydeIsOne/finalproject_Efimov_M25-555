from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from ..infra.settings import SettingsLoader

try:  # optional .env support
    from dotenv import find_dotenv, load_dotenv  # type: ignore
except Exception:  # pragma: no cover - dotenv is optional at runtime
    find_dotenv = None  # type: ignore[assignment]
    load_dotenv = None  # type: ignore[assignment]


# Карты/списки валют
CRYPTO_ID_MAP: Final[dict[str, str]] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

FIAT_CURRENCIES: Final[tuple[str, ...]] = ("EUR", "GBP", "RUB")
CRYPTO_CURRENCIES: Final[tuple[str, ...]] = tuple(CRYPTO_ID_MAP.keys())


@dataclass(frozen=True)
class ParserConfig:
    # Ключ для ExchangeRate-API
    EXCHANGERATE_API_KEY: str | None

    # Эндпоинты
    COINGECKO_URL: str
    COINGECKO_FULL_URL: str | None
    EXCHANGERATE_API_URL: str | None  # Полный URL (если задан)

    # Списки валют
    BASE_CURRENCY: str
    FIAT_CURRENCIES: tuple[str, ...]
    CRYPTO_CURRENCIES: tuple[str, ...]
    CRYPTO_ID_MAP: dict[str, str]

    # Пути
    RATES_FILE_PATH: str
    HISTORY_FILE_PATH: str

    # Сетевые параметры
    REQUEST_TIMEOUT: float


def load_parser_config() -> ParserConfig:
    """Load parser configuration from env/.env and project settings.

    Returns a frozen ParserConfig with API URLs/keys, currency lists, file paths
    and network timeouts. Environment variables override .env; SettingsLoader
    provides defaults for data/logs directories and base currency.
    """
    # Load .env once per process (non-overriding), if available
    try:
        if load_dotenv and find_dotenv:
            path = find_dotenv(usecwd=True)
            if path:
                load_dotenv(dotenv_path=path, override=False)
    except Exception:
        # Ignore .env loading issues silently; fall back to real env
        pass
    settings = SettingsLoader()
    data_dir = os.fspath(settings.get("data_dir"))
    base = str(settings.get("base_currency", "USD") or "USD").upper()
    return ParserConfig(
        EXCHANGERATE_API_KEY=os.getenv("EXCHANGERATE_API_KEY"),
        COINGECKO_URL=os.getenv(
            "COINGECKO_URL", "https://api.coingecko.com/api/v3/simple/price"
        ),
        COINGECKO_FULL_URL=os.getenv("COINGECKO_FULL_URL"),
        EXCHANGERATE_API_URL=os.getenv("EXCHANGERATE_API_URL"),
        BASE_CURRENCY=os.getenv("EXCHANGERATE_BASE", base),
        FIAT_CURRENCIES=FIAT_CURRENCIES,
        CRYPTO_CURRENCIES=CRYPTO_CURRENCIES,
        CRYPTO_ID_MAP=dict(CRYPTO_ID_MAP),
        RATES_FILE_PATH=os.fspath(os.path.join(data_dir, "rates.json")),
        HISTORY_FILE_PATH=os.fspath(os.path.join(data_dir, "exchange_rates.json")),
        REQUEST_TIMEOUT=float(os.getenv("PARSER_HTTP_TIMEOUT", "10")),
    )


def build_exchangerate_url(cfg: ParserConfig) -> str:
    """Собрать URL для ExchangeRate-API."""
    if cfg.EXCHANGERATE_API_URL:
        return cfg.EXCHANGERATE_API_URL
    key = cfg.EXCHANGERATE_API_KEY
    if not key:
        raise RuntimeError(
            "EXCHANGERATE_API_KEY не задан и нет EXCHANGERATE_API_URL; "
            "укажите ключ API в окружении или полный URL"
        )
    base = cfg.BASE_CURRENCY or "USD"
    return f"https://v6.exchangerate-api.com/v6/{key}/latest/{base}"
