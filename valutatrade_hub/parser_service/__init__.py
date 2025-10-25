"""Parser Service package.

Отдельный модуль для получения актуальных курсов из внешних API
и сохранения их в локальное хранилище exchange_rates.json.

Публичная точка входа:
- updater.run_update() — единоразовое обновление
- используется CLI-командой: update-rates
"""

from __future__ import annotations

__all__ = [
    "config",
    "api_clients",
    "storage",
    "updater",
]
