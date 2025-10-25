from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import requests

from ..core.exceptions import ApiRequestError
from .config import ParserConfig, build_exchangerate_url

# no legacy helpers


class BaseApiClient(ABC):
    def __init__(self, cfg: ParserConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def fetch_rates(self) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
        """Возвращает пары и метаданные по ним.

        rates: {"PAIR": rate}
        meta: {"PAIR": {"timestamp": iso, "source": str, ...}}
        """


class ExchangeRateApiClient(BaseApiClient):
    SOURCE = "ExchangeRate-API"

    def fetch_rates(self) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
        url = build_exchangerate_url(self.cfg)
        t0 = time.perf_counter()
        try:
            resp = requests.get(url, timeout=self.cfg.REQUEST_TIMEOUT)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            status = resp.status_code
            etag = resp.headers.get("ETag")
        except requests.exceptions.RequestException as exc:  # type: ignore[attr-defined]
            raise ApiRequestError(f"Network error (ExchangeRate-API): {exc}") from exc

        if status != 200:
            raise ApiRequestError(f"ExchangeRate-API HTTP {status}")

        try:
            data = resp.json()
            if data.get("result") != "success":
                raise ApiRequestError("ExchangeRate-API returned non-success result")
            base = str(data["base_code"]).upper()
            ts_raw = str(data.get("time_last_update_utc"))
            conv = dict(data["conversion_rates"])  # code -> rate_to_base
        except Exception as exc:  # noqa: BLE001
            raise ApiRequestError(f"Malformed ExchangeRate response: {exc}") from exc

        try:
            dt = datetime.strptime(ts_raw, "%a, %d %b %Y %H:%M:%S %z").astimezone(
                timezone.utc
            )
        except Exception:
            dt = datetime.now(timezone.utc)
        ts_iso = dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        rates: dict[str, float] = {}
        meta: dict[str, dict[str, Any]] = {}
        # If PARSER_FIAT_ALL is set, include all fiat codes.
        # Otherwise, only configured FIAT_CURRENCIES.
        use_all = str(os.getenv("PARSER_FIAT_ALL", "0")).strip() in {
            "1",
            "true",
            "True",
        }
        if use_all:
            items = conv.items()
        else:
            wanted = self.cfg.FIAT_CURRENCIES
            items = ((c, conv[c]) for c in wanted if c in conv)
        for code, rate in items:
            try:
                r = float(rate)
            except Exception:  # noqa: BLE001
                continue
            pair = f"{base}_{str(code).upper()}"
            rates[pair] = r
            meta[pair] = {
                "timestamp": ts_iso,
                "source": self.SOURCE,
                "status_code": status,
                "request_ms": elapsed_ms,
                "etag": etag,
                "raw_id": None,
            }
        return rates, meta


class CoinGeckoClient(BaseApiClient):
    SOURCE = "CoinGecko"

    def fetch_rates(self) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
        full = getattr(self.cfg, "COINGECKO_FULL_URL", None)
        if full:
            url = full
        else:
            ids = ",".join(self.cfg.CRYPTO_ID_MAP.values())
            sep = "&" if "?" in self.cfg.COINGECKO_URL else "?"
            url = f"{self.cfg.COINGECKO_URL}{sep}ids={ids}&vs_currencies=usd"
        t0 = time.perf_counter()
        try:
            resp = requests.get(url, timeout=self.cfg.REQUEST_TIMEOUT)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            status = resp.status_code
            etag = resp.headers.get("ETag")
        except requests.exceptions.RequestException as exc:  # type: ignore[attr-defined]
            raise ApiRequestError(f"Network error (CoinGecko): {exc}") from exc

        if status != 200:
            raise ApiRequestError(f"CoinGecko HTTP {status}")

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ApiRequestError(f"Malformed CoinGecko JSON: {exc}") from exc

        ts_iso = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            )
        )

        rates: dict[str, float] = {}
        meta: dict[str, dict[str, Any]] = {}
        for ticker, cid in self.cfg.CRYPTO_ID_MAP.items():
            info = data.get(cid)
            if not isinstance(info, dict):
                continue
            usd = info.get("usd")
            if usd is None:
                continue
            try:
                r = float(usd)
            except Exception:  # noqa: BLE001
                continue
            pair = f"{ticker}_USD"
            rates[pair] = r
            meta[pair] = {
                "timestamp": ts_iso,
                "source": self.SOURCE,
                "status_code": status,
                "request_ms": elapsed_ms,
                "etag": etag,
                "raw_id": cid,
            }
        return rates, meta
