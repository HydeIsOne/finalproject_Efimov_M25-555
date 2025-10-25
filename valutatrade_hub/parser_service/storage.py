from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from ..infra.settings import SettingsLoader
from .config import load_parser_config


def _data_dir() -> Path:
    settings = SettingsLoader()
    return Path(settings.get("data_dir"))


def exchange_rates_path() -> Path:
    cfg = load_parser_config()
    return Path(cfg.HISTORY_FILE_PATH)


def rates_snapshot_path() -> Path:
    cfg = load_parser_config()
    return Path(cfg.RATES_FILE_PATH)


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def ensure_storage() -> None:
    h = exchange_rates_path()
    h.parent.mkdir(parents=True, exist_ok=True)
    if not h.exists():
        h.write_text("[]", encoding="utf-8")
    r = rates_snapshot_path()
    if not r.exists():
        _atomic_write_json(r, {"pairs": {}, "last_refresh": None})


def read_exchange_rates() -> list[dict[str, Any]]:
    ensure_storage()
    text = exchange_rates_path().read_text(encoding="utf-8")
    return list(json.loads(text) if text else [])


def append_history(records: Iterable[dict[str, Any]]) -> int:
    """Append unique records with atomic write. Returns number added."""
    ensure_storage()
    path = exchange_rates_path()
    try:
        current = read_exchange_rates()
    except Exception:
        current = []
    seen_ids = {str(rec.get("id")) for rec in current if isinstance(rec, dict)}
    to_add: list[dict[str, Any]] = []
    for rec in records:
        rid = str(rec.get("id"))
        if not rid or rid in seen_ids:
            continue
        to_add.append(rec)
        seen_ids.add(rid)
    if not to_add:
        return 0
    new_all = [*current, *to_add]
    _atomic_write_json(path, new_all)
    return len(to_add)


def clear_history() -> int:
    """Clear the history file (exchange_rates.json).

    Returns number of removed records.
    """
    ensure_storage()
    path = exchange_rates_path()
    try:
        current = read_exchange_rates()
    except Exception:
        current = []
    _atomic_write_json(path, [])
    return len(current)


def read_snapshot() -> dict[str, Any]:
    ensure_storage()
    path = rates_snapshot_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"pairs": {}, "last_refresh": None}


def write_snapshot_pairs(
    new_pairs: dict[str, dict[str, Any]], last_refresh: str
) -> None:
    """Write snapshot.

    By default, merges pairs honoring updated_at freshness.
    If env PARSER_SNAPSHOT_STRICT=1, replaces snapshot with exactly new_pairs.
    """
    # Strict mode: replace snapshot with exactly the provided pairs
    strict = False
    try:
        strict = str(os.getenv("PARSER_SNAPSHOT_STRICT", "0")).strip() in {
            "1",
            "true",
            "True",
        }
    except Exception:
        strict = False
    if strict:
        out = {"pairs": dict(new_pairs), "last_refresh": last_refresh}
        _atomic_write_json(rates_snapshot_path(), out)
        return

    # Default: merge with freshness
    snap = read_snapshot()
    pairs = dict(snap.get("pairs") or {})

    def _is_newer(ts_new: str | None, ts_old: str | None) -> bool:
        from datetime import datetime

        def _parse(ts: str | None) -> datetime:
            if not ts:
                return datetime.min
            s = ts.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return datetime.min

        return _parse(ts_new) >= _parse(ts_old)

    for key, obj in new_pairs.items():
        cur = pairs.get(key)
        if not isinstance(cur, dict) or _is_newer(
            obj.get("updated_at"), cur.get("updated_at")
        ):
            pairs[key] = obj

    out = {"pairs": pairs, "last_refresh": last_refresh}
    _atomic_write_json(rates_snapshot_path(), out)
