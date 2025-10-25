from __future__ import annotations

import os
import time
from datetime import datetime


def maybe_auto_update_on_start(command: str | None) -> None:
    """Perform a best-effort daily auto-update at app start.

    - Controlled by env PARSER_AUTO_UPDATE_ON_START (default enabled: 1)
    - Skips if the explicit command is 'update-rates' or 'clear-history'
    - Compares data/rates.json 'last_refresh' date with current date
    - If last_refresh is missing or from previous day, triggers update
    """
    # Toggle to opt out
    flag = str(os.getenv("PARSER_AUTO_UPDATE_ON_START", "1")).strip()
    if flag in {"0", "false", "False"}:
        return

    if command in {"update-rates", "clear-history"}:
        return

    try:
        from .storage import read_snapshot
        from .updater import run_update
    except Exception:
        return

    try:
        snap = read_snapshot()
        last = str(snap.get("last_refresh") or "")
        last_dt = None
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except Exception:
                last_dt = None

        now = datetime.now()
        need_daily = last_dt is None or last_dt.date() < now.date()
        if need_daily:
            summary = run_update(source=None)
            print(
                "[auto] Курсы обновлены при запуске: "
                f"fiat={summary.get('fiat', 0)}, crypto={summary.get('crypto', 0)}"
            )
    except Exception:
        # Do not block the CLI on any error here.
        return

def run_periodic(interval_seconds: float, source: str | None = None) -> None:
    """Run updates periodically until interrupted (Ctrl+C).

    interval_seconds: seconds between runs; minimum enforced to 1.0
    source: optional specific source ("coingecko" or "exchangerate")
    """
    try:
        from .updater import run_update
    except Exception:
        return
    interval = max(1.0, float(interval_seconds))
    print(
        f"[schedule] Starting periodic updates every {interval:.1f}s"
        + (f" (source={source})" if source else "")
        + ". Press Ctrl+C to stop."
    )
    while True:
        try:
            summary = run_update(source=source)
            print(
                "[schedule] Updated: "
                f"fiat={summary.get('fiat', 0)}, crypto={summary.get('crypto', 0)}"
            )
        except KeyboardInterrupt:
            print("[schedule] Stopped by user")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[schedule] Update error: {exc}")
        time.sleep(interval)
