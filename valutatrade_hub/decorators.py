from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from .infra.settings import SettingsLoader  # noqa: F401 - future use

_logger = logging.getLogger("valutatrade")


def log_action(
    action: str, verbose: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to log domain actions at INFO level.

    Logs timestamp ISO, action, user_id/username if available, currency_code, amount,
    rate/base when present, and result (OK/ERROR). Does not swallow exceptions.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Uniform ISO timestamp without microseconds, UTC 'Z' suffix
            ts = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            try:
                result = func(*args, **kwargs)
                # Best-effort extraction of common fields
                user_id = kwargs.get("user_id")
                if action in {"BUY", "SELL"}:
                    if user_id is None and args and isinstance(args[0], int):
                        user_id = args[0]
                # Extract username safely
                username = kwargs.get("username")
                if action in {"REGISTER", "LOGIN"}:
                    if username is None and args and isinstance(args[0], str):
                        # For register/login first positional is username
                        username = args[0]
                # Extract currency/amount only for BUY/SELL to avoid logging passwords
                currency_code = None
                amount = None
                if action in {"BUY", "SELL"}:
                    currency_code = kwargs.get(
                        "currency_code", args[1] if len(args) > 1 else None
                    )
                    amount = kwargs.get("amount", args[2] if len(args) > 2 else None)
                rate = None
                base = None
                if isinstance(result, dict):
                    # If use case returned user_id (e.g., LOGIN/REGISTER), capture it
                    if user_id is None and "user_id" in result:
                        try:
                            user_id = int(result.get("user_id"))
                        except Exception:  # noqa: BLE001
                            user_id = result.get("user_id")
                    rate = result.get("rate_usd") or result.get("rate")
                    base = "USD" if "rate_usd" in result else None
                extra = ""
                if verbose and isinstance(result, dict):
                    extra = f" details={{{result}}}"
                _logger.info(
                    (
                        "%(ts)s %(action)s user_id=%(uid)s username='%(uname)s' "
                        "currency='%(cur)s' amount=%(amt)s rate=%(rate)s "
                        "base='%(base)s' result=OK"
                    )
                    .replace("%(ts)s", ts)
                    .replace("%(action)s", action)
                    .replace("%(uid)s", str(user_id))
                    .replace("%(uname)s", str(username))
                    .replace("%(cur)s", str(currency_code))
                    .replace("%(amt)s", str(amount))
                    .replace("%(rate)s", str(rate))
                    .replace("%(base)s", str(base))
                )
                if extra:
                    _logger.info(extra)
                return result
            except Exception as exc:  # noqa: BLE001
                user_id = kwargs.get("user_id")
                if action in {"BUY", "SELL"}:
                    if user_id is None and args and isinstance(args[0], int):
                        user_id = args[0]
                username = kwargs.get("username")
                if action in {"REGISTER", "LOGIN"}:
                    if username is None and args and isinstance(args[0], str):
                        username = args[0]
                currency_code = None
                amount = None
                if action in {"BUY", "SELL"}:
                    currency_code = kwargs.get(
                        "currency_code", args[1] if len(args) > 1 else None
                    )
                    amount = kwargs.get("amount", args[2] if len(args) > 2 else None)
                _logger.info(
                    (
                        "%(ts)s %(action)s user_id=%(uid)s username='%(uname)s' "
                        "currency='%(cur)s' amount=%(amt)s result=ERROR "
                        "error_type=%(etype)s error_message='%(emsg)s'"
                    )
                    .replace("%(ts)s", ts)
                    .replace("%(action)s", action)
                    .replace("%(uid)s", str(user_id))
                    .replace("%(uname)s", str(username))
                    .replace("%(cur)s", str(currency_code))
                    .replace("%(amt)s", str(amount))
                    .replace("%(etype)s", type(exc).__name__)
                    .replace("%(emsg)s", str(exc).replace("'", "\\'"))
                )
                raise

        return wrapper

    return decorator
