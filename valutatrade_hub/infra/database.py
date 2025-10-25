from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import SettingsLoader


class DatabaseManager:
    """Singleton JSON database manager."""

    _instance: "DatabaseManager | None" = None

    def __new__(cls, *args, **kwargs):  # noqa: D401
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._settings = SettingsLoader()
        self._data_dir = Path(self._settings.get("data_dir"))
        self._users = self._data_dir / "users.json"
        self._portfolios = self._data_dir / "portfolios.json"
        self._rates = self._data_dir / "rates.json"
        for p in (self._users, self._portfolios, self._rates):
            if not p.exists():
                p.write_text("[]" if p.name != "rates.json" else "{}", encoding="utf-8")

    def _read_json(self, path: Path) -> Any:
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text) if text else None
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Corrupted JSON at {path}: {exc}") from exc

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Public API
    def read_users(self) -> list[dict[str, Any]]:
        return list(self._read_json(self._users) or [])

    def write_users(self, rows: list[dict[str, Any]]) -> None:
        self._write_json(self._users, rows)

    def read_portfolios(self) -> list[dict[str, Any]]:
        return list(self._read_json(self._portfolios) or [])

    def write_portfolios(self, rows: list[dict[str, Any]]) -> None:
        self._write_json(self._portfolios, rows)

    def read_rates(self) -> dict[str, Any]:
        return dict(self._read_json(self._rates) or {})

    def write_rates(self, obj: dict[str, Any]) -> None:
        self._write_json(self._rates, obj)
