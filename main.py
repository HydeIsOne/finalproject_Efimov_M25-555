"""Entrypoint for running the CLI directly via `python main.py`.

Functionality will be implemented in subsequent steps.
"""

from __future__ import annotations


def main() -> None:
    # Отложенно: подключение и запуск CLI из valutatrade_hub.cli.interface
    try:
        from valutatrade_hub.cli.interface import main as cli_main

        cli_main()
    except Exception as exc:  # noqa: BLE001 - базовый каркас, перехватываем всё
        print(f"Ошибка запуска CLI: {exc}")


if __name__ == "__main__":
    main()
