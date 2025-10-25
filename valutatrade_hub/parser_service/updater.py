from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from ..logging_config import configure_logging
from .api_clients import CoinGeckoClient, ExchangeRateApiClient
from .config import load_parser_config
from .storage import append_history, write_snapshot_pairs


class RatesUpdater:
    """Orchestrates fetching from providers, history append, and snapshot write.

    - Aggregates ExchangeRate-API and CoinGecko clients
    - Appends unique records to exchange_rates.json (unless disabled)
    - Writes bidirectional pairs into rates.json (strict merge mode configurable)
    """
    def __init__(self) -> None:
        self.cfg = load_parser_config()
        self.clients = {
            "exchangerate": ExchangeRateApiClient(self.cfg),
            "coingecko": CoinGeckoClient(self.cfg),
        }

    def run_update(self, source: str | None = None) -> dict[str, Any]:
        """Run one update cycle.

        Args:
            source: Optional specific provider ("exchangerate" or "coingecko").
        Returns:
            Summary counters: {"fiat": int, "crypto": int, "added": int}.
        """
        configure_logging()
        logger = logging.getLogger("valutatrade")
        logger.info("Starting rates update...")

        # Fetch from clients
        rates_all: dict[str, float] = {}
        meta_all: dict[str, dict[str, Any]] = {}
        counters: dict[str, int] = {"exchangerate": 0, "coingecko": 0}
        sources = [source] if source else list(self.clients.keys())
        for name in sources:
            client = self.clients.get(name)
            if not client:
                continue
            try:
                pretty = "CoinGecko" if name == "coingecko" else "ExchangeRate-API"
                logger.info("Fetching from %s...", pretty)
                rates, meta = client.fetch_rates()
                counters[name] = len(rates)
                rates_all.update(rates)
                meta_all.update(meta)
                logger.info("Fetching from %s... OK (%d rates)", pretty, counters[name])
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to fetch from %s: %s", name, exc
                )

        # Build and append unique history rows
        history_rows: list[dict[str, Any]] = []
        for pair, rate in rates_all.items():
            meta = meta_all.get(pair, {})
            frm, to = pair.split("_", 1)
            ts = str(
                meta.get("timestamp")
                or datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            rec_id = f"{frm}_{to}_{ts}"
            history_rows.append(
                {
                    "id": rec_id,
                    "from_currency": frm,
                    "to_currency": to,
                    "rate": float(rate),
                    "timestamp": ts,
                    "source": str(meta.get("source") or "Unknown"),
                    "meta": {
                        "raw_id": meta.get("raw_id"),
                        "request_ms": meta.get("request_ms"),
                        "status_code": meta.get("status_code"),
                        "etag": meta.get("etag"),
                    },
                }
            )
        # Optionally disable history appending for this run
        history_off = str(os.getenv("PARSER_HISTORY_DISABLED", "0")).strip() in {
            "1",
            "true",
            "True",
        }
        if history_off:
            logger.info(
                "History append disabled for this run (PARSER_HISTORY_DISABLED=1)"
            )
            added = 0
        else:
            added = append_history(history_rows)
            logger.info("Appended %d unique records to exchange_rates.json", added)

        # Build snapshot pairs (both directions)
        pairs: dict[str, dict[str, Any]] = {}
        for pair, rate in rates_all.items():
            meta = meta_all.get(pair, {})
            ts = str(meta.get("timestamp"))
            src = str(meta.get("source") or "Unknown")
            frm, to = pair.split("_", 1)
            try:
                r = float(rate)
                if r <= 0:
                    continue
            except Exception:
                continue
            fwd = pair
            inv = f"{to}_{frm}"
            pairs[fwd] = {"rate": r, "updated_at": ts, "source": src}
            pairs[inv] = {"rate": 1.0 / r, "updated_at": ts, "source": src}

        now_iso = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        # Log snapshot write intent (strict flag from env)
        strict = str(os.getenv("PARSER_SNAPSHOT_STRICT", "0")).strip() in {
            "1",
            "true",
            "True",
        }
        logger.info(
            "Writing %d rates to data/rates.json (strict=%s)...",
            len(pairs),
            str(strict).lower(),
        )
        write_snapshot_pairs(pairs, now_iso)
        logger.info("Update successful. Last refresh: %s", now_iso)

        return {
            "fiat": counters.get("exchangerate", 0),
            "crypto": counters.get("coingecko", 0),
            "added": added,
        }


def run_update(source: str | None = None) -> dict[str, Any]:
    """Convenience function to run an update without instantiating the class."""
    return RatesUpdater().run_update(source=source)
