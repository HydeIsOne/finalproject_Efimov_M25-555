"""Business use-cases for ValutaTrade Hub.

Функции работы с данными (JSON-персистентность) и базовые операции:
- регистрация и вход пользователя;
- управление портфелем: кошельки, покупка/продажа;
- получение курсов: из локального кеша с заглушкой по умолчанию.

CLI должен только вызывать эти функции и форматировать вывод.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..decorators import log_action
from ..infra.database import DatabaseManager
from ..infra.settings import SettingsLoader
from . import currencies as cur
from .exceptions import CurrencyNotFoundError, InsufficientFundsError
from .models import DomainError, User

_SETTINGS = SettingsLoader()
# Paths
DATA_DIR = Path(_SETTINGS.get("data_dir", "data"))
USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"
# Session file in system temp dir, unique per project path
_PROJECT_ID = hashlib.sha1(
    str(Path(__file__).resolve().parents[2]).encode("utf-8")
).hexdigest()[:8]
SESSION_FILE = Path(tempfile.gettempdir()) / f"vth_session_{_PROJECT_ID}.json"

# Rates config from settings
RATES_MAX_AGE_SECONDS = int(_SETTINGS.get("rates_ttl_seconds", 300))


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]", encoding="utf-8")
    if not PORTFOLIOS_FILE.exists():
        PORTFOLIOS_FILE.write_text("[]", encoding="utf-8")
    if not RATES_FILE.exists():
        RATES_FILE.write_text("{}", encoding="utf-8")


def _read_json(path: Path) -> Any:
    # Delegate to DatabaseManager for centralized access
    db = DatabaseManager()
    if path == USERS_FILE:
        return db.read_users()
    if path == PORTFOLIOS_FILE:
        return db.read_portfolios()
    if path == RATES_FILE:
        return db.read_rates()
    # Fallback
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text else None
    except Exception as exc:  # noqa: BLE001
        raise DomainError(f"Failed to read JSON at {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    db = DatabaseManager()
    try:
        if path == USERS_FILE:
            db.write_users(list(data or []))
        elif path == PORTFOLIOS_FILE:
            db.write_portfolios(list(data or []))
        elif path == RATES_FILE:
            db.write_rates(dict(data or {}))
        else:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001
        raise DomainError(f"Failed to write JSON at {path}: {exc}") from exc


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------ Users ------------------


def list_users() -> list[dict[str, Any]]:
    """Return all users as JSON-serializable rows.

    Returns:
        List of user dicts from users.json.
    """
    _ensure_data_files()
    users = _read_json(USERS_FILE)
    return list(users or [])


def find_user_by_username(username: str) -> dict[str, Any] | None:
    """Find user row by username.

    Args:
        username: Case-sensitive stored username.
    Returns:
        Matching user dict or None.
    """
    uname = (username or "").strip()
    for u in list_users():
        if u.get("username") == uname:
            return u
    return None


def find_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Find user row by numeric id or return None."""
    for u in list_users():
        if int(u.get("user_id", -1)) == int(user_id):
            return u
    return None


def _generate_user_id(users: list[dict[str, Any]]) -> int:
    if not users:
        return 1
    return max(int(u.get("user_id", 0)) for u in users) + 1


@log_action("REGISTER")
def register_user(username: str, password: str) -> dict[str, Any]:
    """Register a new user.

    Validates name and minimal password length, ensures uniqueness, persists
    the user and creates an empty portfolio.

    Args:
        username: Desired username.
        password: Plain password (min 4 chars).
    Returns:
        Minimal info: {"user_id": int, "username": str}.
    Raises:
        DomainError: On invalid input or if username already taken.
    """
    uname = (username or "").strip()
    if not uname:
        raise DomainError("Имя пользователя не может быть пустым")
    if len(password or "") < 4:
        raise DomainError("Пароль должен быть не короче 4 символов")
    _ensure_data_files()
    users = list_users()
    if any(u.get("username") == uname for u in users):
        raise DomainError(f"Имя пользователя '{uname}' уже занято")

    salt = secrets.token_hex(4)
    reg_date = _now().replace(microsecond=0)

    # Create transient User to reuse hashing behavior
    tmp_user = User(
        user_id=0,
        username=uname,
        hashed_password="x",
        salt=salt,
        registration_date=reg_date,
    )
    tmp_user.change_password(password)

    user_id = _generate_user_id(users)
    user_row = {
        "user_id": user_id,
        "username": uname,
        "hashed_password": tmp_user.hashed_password,
        "salt": tmp_user.salt,
        "registration_date": reg_date.isoformat(),
    }
    users.append(user_row)
    _write_json(USERS_FILE, users)

    # Create empty portfolio
    portfolios = list_portfolios()
    portfolios.append({"user_id": user_id, "wallets": {}})
    _write_json(PORTFOLIOS_FILE, portfolios)

    # Return minimal info
    return {"user_id": user_id, "username": uname}


@log_action("LOGIN")
def login_user(username: str, password: str) -> dict[str, Any]:
    """Authenticate user and persist a local session.

    Args:
        username: Existing username.
        password: Plain password.
    Returns:
        {"user_id": int, "username": str}
    Raises:
        DomainError: If user not found or password mismatch.
    """
    uname = (username or "").strip()
    if not uname:
        raise DomainError("Имя пользователя не может быть пустым")
    u = find_user_by_username(uname)
    if not u:
        raise DomainError(f"Пользователь '{uname}' не найден")

    # Verify using User model
    user_obj = User(
        user_id=int(u["user_id"]),
        username=str(u["username"]),
        hashed_password=str(u["hashed_password"]),
        salt=str(u["salt"]),
        registration_date=datetime.fromisoformat(str(u["registration_date"])),
    )
    if not user_obj.verify_password(password or ""):
        raise DomainError("Неверный пароль")

    # Persist session
    _write_json(
        SESSION_FILE,
        {"user_id": user_obj.user_id, "username": user_obj.username},
    )
    return {"user_id": user_obj.user_id, "username": user_obj.username}


def current_session() -> dict[str, Any] | None:
    """Return current session dict or None if not logged in."""
    _ensure_data_files()
    data = _read_json(SESSION_FILE) or {}
    if "user_id" in data and "username" in data:
        return {"user_id": int(data["user_id"]), "username": str(data["username"])}
    return None


def require_login() -> dict[str, Any]:
    """Ensure session exists and return it, else raise DomainError."""
    sess = current_session()
    if not sess:
        raise DomainError("Сначала выполните login")
    return sess


def logout_user() -> None:
    """Clear current session data (logout)."""
    _ensure_data_files()
    _write_json(SESSION_FILE, {})


# ------------------ Portfolios ------------------


def list_portfolios() -> list[dict[str, Any]]:
    """Return all portfolios as JSON-serializable rows."""
    _ensure_data_files()
    ports = _read_json(PORTFOLIOS_FILE)
    return list(ports or [])


def get_portfolio_row(user_id: int) -> dict[str, Any]:
    """Get portfolio row for a user or raise DomainError if missing."""
    for p in list_portfolios():
        if int(p.get("user_id", -1)) == int(user_id):
            return p
    raise DomainError("Портфель пользователя не найден")


def save_portfolio_row(row: dict[str, Any]) -> None:
    """Upsert a portfolio row by user_id to portfolios.json."""
    rows = list_portfolios()
    uid = int(row.get("user_id", -1))
    replaced = False
    for i, existing in enumerate(rows):
        if int(existing.get("user_id", -1)) == uid:
            rows[i] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    _write_json(PORTFOLIOS_FILE, rows)


def add_currency(user_id: int, currency_code: str) -> None:
    """Ensure wallet exists for currency in user's portfolio (no-op if exists)."""
    code = (currency_code or "").strip().upper()
    if not code:
        raise DomainError("currency_code не может быть пустым")
    row = get_portfolio_row(user_id)
    wallets = dict(row.get("wallets", {}))
    if code in wallets:
        return
    wallets[code] = {"balance": 0.0}
    row["wallets"] = wallets
    save_portfolio_row(row)


def adjust_wallet(user_id: int, currency_code: str, delta: float) -> dict[str, Any]:
    """Adjust wallet balance by delta and persist.

    Args:
        user_id: Portfolio owner id.
        currency_code: Wallet currency (e.g., "USD").
        delta: Positive to deposit, negative to withdraw.
    Returns:
        Updated wallet dict: {"balance": float}.
    Raises:
        DomainError: On invalid input or insufficient funds.
    """
    code = (currency_code or "").strip().upper()
    if not code:
        raise DomainError("currency_code не может быть пустым")
    row = get_portfolio_row(user_id)
    wallets = dict(row.get("wallets", {}))
    cur = wallets.get(code, {"balance": 0.0})
    new_balance = float(cur.get("balance", 0.0)) + float(delta)
    if new_balance < 0:
        raise DomainError("Недостаточно средств")
    cur["balance"] = round(new_balance, 12)
    wallets[code] = cur
    row["wallets"] = wallets
    save_portfolio_row(row)
    return cur


# ------------------ Rates ------------------


def _default_rates_to_usd() -> dict[str, float]:
    return {
        "USD": 1.0,
        "EUR": 1.0786,
        "BTC": 59337.21,
        "ETH": 3720.0,
        "RUB": 0.01016,
    }


def _pair_key(frm: str, to: str) -> str:
    return f"{frm}_{to}"


def _load_rates() -> dict[str, Any]:
    _ensure_data_files()
    obj = _read_json(RATES_FILE)
    return dict(obj or {})


def _save_rates(obj: dict[str, Any]) -> None:
    _write_json(RATES_FILE, obj)


def get_rate(frm: str, to: str) -> dict[str, Any]:
    """Get rate frm→to using local cache or defaults.

    Args:
        frm: Source currency code.
        to: Target currency code.
    Returns:
        {"rate": float, "updated_at": ISO-8601 str, "source": str}
    Raises:
        CurrencyNotFoundError: If currency code unknown.
        DomainError: If conversion not possible.
    """
    f = (frm or "").strip().upper()
    t = (to or "").strip().upper()
    if not f or not t:
        raise CurrencyNotFoundError(f or t)
    # Validate via currencies registry
    cur.get_currency(f)
    cur.get_currency(t)
    if f == t:
        # Normalize timestamp to second precision for consistent display
        return {
            "rate": 1.0,
            "updated_at": _now().replace(microsecond=0).isoformat(),
            "source": "local",
        }

    cache = _load_rates()
    key = _pair_key(f, t)
    pairs_section = cache.get("pairs") if isinstance(cache, dict) else None
    if isinstance(pairs_section, dict):
        entry = pairs_section.get(key)
    else:
        entry = cache.get(key)

    def _is_fresh(ts: str | None) -> bool:
        if not ts:
            return False
        try:
            updated = datetime.fromisoformat(ts)
        except ValueError:
            return False
        return (_now() - updated) <= timedelta(seconds=RATES_MAX_AGE_SECONDS)

    if isinstance(entry, dict) and _is_fresh(entry.get("updated_at")):
        return {
            "rate": float(entry["rate"]),
            "updated_at": entry["updated_at"],
            "source": entry.get("source", cache.get("source", "cache")),
        }

    # Try refresh via local stub (Parser Service placeholder)
    # If refresh fails in future (real API), raise ApiRequestError
    # For now, use local defaults as a "successful" refresh
    def_rates = _default_rates_to_usd()
    if f == "USD" and t in def_rates:
        rate = 1.0 / def_rates[t]
    elif t == "USD" and f in def_rates:
        rate = def_rates[f]
    elif f in def_rates and t in def_rates:
        # f->USD then USD->t
        rate = def_rates[f] / def_rates[t]
    else:
        raise DomainError(f"Курс {f}→{t} недоступен. Повторите попытку позже.")

    ts = _now().replace(microsecond=0).isoformat()
    # Write back honoring new snapshot structure if present
    if isinstance(pairs_section, dict):
        pairs_section[key] = {"rate": rate, "updated_at": ts, "source": "LocalStub"}
        cache["pairs"] = pairs_section
        cache["last_refresh"] = ts
    else:
        cache[key] = {"rate": rate, "updated_at": ts}
        cache["source"] = cache.get("source", "LocalStub")
        cache["last_refresh"] = ts
    _save_rates(cache)
    return {"rate": rate, "updated_at": ts, "source": "LocalStub"}


# ------------------ Operations ------------------


def show_portfolio(user_id: int, base_currency: str = "USD") -> dict[str, Any]:
    """Compute portfolio total and wallet details in base currency.

    Args:
        user_id: Portfolio owner id.
        base_currency: Target base (default: USD).
    Returns:
        {"base": str, "total": float, "wallets": list[dict]} with per-wallet
        value and last rate timestamp.
    """
    row = get_portfolio_row(user_id)
    wallets = dict(row.get("wallets", {}))
    base = (base_currency or "USD").strip().upper()

    total_base = 0.0
    details: list[dict[str, Any]] = []
    for code, data in wallets.items():
        bal = float(data.get("balance", 0.0))
        if bal == 0:
            details.append({"currency": code, "balance": bal, "value": 0.0})
            continue
        rate_info = get_rate(code, base)
        value = bal * float(rate_info["rate"])
        total_base += value
        details.append({
            "currency": code,
            "balance": bal,
            "value": value,
            "rate": rate_info["rate"],
            "updated_at": rate_info["updated_at"],
        })

    return {"base": base, "total": round(total_base, 8), "wallets": details}


@log_action("BUY")
def buy_currency(
    user_id: int, currency_code: str, amount: float, username: str | None = None
) -> dict[str, Any]:
    """Buy amount of currency for USD at current rate.

    Ensures wallets, checks funds, debits USD and credits target currency.

    Args:
        user_id: Buyer id.
        currency_code: Currency to buy (e.g., "EUR").
        amount: Quantity to buy (> 0).
        username: Optional for logging context.
    Returns:
        {"currency", "amount", "rate_usd", "cost_usd", "new_balance"}.
    Raises:
        CurrencyNotFoundError: Unknown currency.
        InsufficientFundsError: Not enough USD balance.
        DomainError: Invalid amount or state errors.
    """
    code = (currency_code or "").strip().upper()
    if not code:
        raise CurrencyNotFoundError(code)
    # Validate currency code exists
    cur.get_currency(code)
    try:
        amt = float(amount)
    except (TypeError, ValueError) as exc:
        raise DomainError("'amount' должен быть положительным числом") from exc
    if amt <= 0:
        raise DomainError("'amount' должен быть положительным числом")

    # Ensure wallet exists
    add_currency(user_id, code)

    # Price in USD
    rate_info = get_rate(code, "USD")
    cost_usd = amt * float(rate_info["rate"])

    # Deduct from USD wallet
    add_currency(user_id, "USD")
    # Will raise InsufficientFundsError on insufficient funds
    row = get_portfolio_row(user_id)
    bal_usd = float(
        dict(row.get("wallets", {}))
        .get("USD", {"balance": 0.0})
        .get("balance", 0.0)
    )
    if bal_usd < cost_usd:
        raise InsufficientFundsError(bal_usd, cost_usd, "USD")
    adjust_wallet(user_id, "USD", -cost_usd)

    # Credit target wallet
    new_wallet = adjust_wallet(user_id, code, amt)

    return {
        "currency": code,
        "amount": amt,
        "rate_usd": rate_info["rate"],
        "cost_usd": cost_usd,
        "new_balance": new_wallet["balance"],
    }


@log_action("SELL")
def sell_currency(
    user_id: int, currency_code: str, amount: float, username: str | None = None
) -> dict[str, Any]:
    """Sell amount of currency for USD at current rate.

    Debits the currency wallet and credits USD wallet.

    Args:
        user_id: Seller id.
        currency_code: Currency to sell.
        amount: Quantity to sell (> 0).
        username: Optional for logging context.
    Returns:
        {"currency", "amount", "rate_usd", "proceeds_usd", "new_balance"}.
    Raises:
        CurrencyNotFoundError: Unknown currency.
        InsufficientFundsError: Not enough currency balance.
        DomainError: Invalid amount or state errors.
    """
    code = (currency_code or "").strip().upper()
    if not code:
        raise CurrencyNotFoundError(code)
    # Validate currency code exists
    cur.get_currency(code)
    try:
        amt = float(amount)
    except (TypeError, ValueError) as exc:
        raise DomainError("'amount' должен быть положительным числом") from exc
    if amt <= 0:
        raise DomainError("'amount' должен быть положительным числом")

    # Ensure wallet exists and has funds
    row = get_portfolio_row(user_id)
    bal = float(
        dict(row.get("wallets", {})).get(code, {"balance": 0.0}).get("balance", 0.0)
    )
    if bal < amt:
        raise InsufficientFundsError(bal, amt, code)

    # Price in USD
    rate_info = get_rate(code, "USD")
    proceeds_usd = amt * float(rate_info["rate"])

    # Debit currency wallet
    new_wallet = adjust_wallet(user_id, code, -amt)

    # Credit USD wallet
    add_currency(user_id, "USD")
    adjust_wallet(user_id, "USD", proceeds_usd)

    return {
        "currency": code,
        "amount": amt,
        "rate_usd": rate_info["rate"],
        "proceeds_usd": proceeds_usd,
        "new_balance": new_wallet["balance"],
    }

