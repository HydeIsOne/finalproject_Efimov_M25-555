from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


class SettingsLoader:
    """Singleton settings provider.

    Reads pyproject.toml [tool.valutatrade] if present.
    Provides defaults otherwise.
    """

    _instance: "SettingsLoader | None" = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):  # noqa: D401 - singleton boilerplate
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._root = Path(__file__).resolve().parents[2]
        self._config: dict[str, Any] = {}
        self.reload()

    def _defaults(self) -> dict[str, Any]:
        root = self._root
        return {
            "data_dir": str(root / "data"),
            "logs_dir": str(root / "logs"),
            "log_file": str(root / "logs" / "actions.log"),
            "log_level": "INFO",
            "log_rotation_bytes": 1_048_576,  # 1MB
            "log_backup_count": 5,
            "base_currency": "USD",
            "rates_ttl_seconds": 300,
        }

    def reload(self) -> None:
        cfg = self._defaults()
        pyproject = self._root / "pyproject.toml"
        if tomllib and pyproject.exists():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                vt = data.get("tool", {}).get("valutatrade", {})  # type: ignore[assignment]
                if isinstance(vt, dict):
                    for k, v in vt.items():
                        cfg[k] = v
            except Exception:
                # Ignore malformed config; stick to defaults
                pass
        self._config = cfg
        # Ensure dirs exist
        Path(self._config["data_dir"]).mkdir(parents=True, exist_ok=True)
        Path(self._config["logs_dir"]).mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._config.get(key, default)
