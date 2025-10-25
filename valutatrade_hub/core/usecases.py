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

from .models import DomainError, User

# Paths
DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"
# Session file in system temp dir, unique per project path
_PROJECT_ID = hashlib.sha1(
    str(Path(__file__).resolve().parents[2]).encode("utf-8")
).hexdigest()[:8]
SESSION_FILE = Path(tempfile.gettempdir()) / f"vth_session_{_PROJECT_ID}.json"

# Rates config
RATES_MAX_AGE_SECONDS = 300  # 5 minutes


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]", encoding="utf-8")
    if not PORTFOLIOS_FILE.exists():
        PORTFOLIOS_FILE.write_text("[]", encoding="utf-8")
    if not RATES_FILE.exists():
        RATES_FILE.write_text("{}", encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text else None
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise DomainError(f"Corrupted JSON at {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise DomainError(f"Failed to write JSON at {path}: {exc}") from exc


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------ Users ------------------


def list_users() -> list[dict[str, Any]]:
    _ensure_data_files()
    users = _read_json(USERS_FILE)
    return list(users or [])


def find_user_by_username(username: str) -> dict[str, Any] | None:
    uname = (username or "").strip()
    for u in list_users():
        if u.get("username") == uname:
            return u
    return None


def _generate_user_id(users: list[dict[str, Any]]) -> int:
    if not users:
        return 1
    return max(int(u.get("user_id", 0)) for u in users) + 1


def register_user(username: str, password: str) -> dict[str, Any]:
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


def login_user(username: str, password: str) -> dict[str, Any]:
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
    _ensure_data_files()
    data = _read_json(SESSION_FILE) or {}
    if "user_id" in data and "username" in data:
        return {"user_id": int(data["user_id"]), "username": str(data["username"])}
    return None


def require_login() -> dict[str, Any]:
    sess = current_session()
    if not sess:
        raise DomainError("Сначала выполните login")
    return sess


def logout_user() -> None:
    _ensure_data_files()
    _write_json(SESSION_FILE, {})


# ------------------ Portfolios ------------------


def list_portfolios() -> list[dict[str, Any]]:
    _ensure_data_files()
    ports = _read_json(PORTFOLIOS_FILE)
    return list(ports or [])


def get_portfolio_row(user_id: int) -> dict[str, Any]:
    for p in list_portfolios():
        if int(p.get("user_id", -1)) == int(user_id):
            return p
    raise DomainError("Портфель пользователя не найден")


def save_portfolio_row(row: dict[str, Any]) -> None:
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

    Returns dict: {"rate": float, "updated_at": iso, "source": str}
    """
    f = (frm or "").strip().upper()
    t = (to or "").strip().upper()
    if not f or not t:
        raise DomainError("Коды валют не должны быть пустыми")
    if f == t:
        return {"rate": 1.0, "updated_at": _now().isoformat(), "source": "local"}

    cache = _load_rates()
    key = _pair_key(f, t)
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
            "source": cache.get("source", "cache"),
        }

    # Fallback to defaults (via USD bridge if needed)
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
    cache[key] = {"rate": rate, "updated_at": ts}
    cache["source"] = cache.get("source", "LocalStub")
    cache["last_refresh"] = ts
    _save_rates(cache)
    return {"rate": rate, "updated_at": ts, "source": cache["source"]}


# ------------------ Operations ------------------


def show_portfolio(user_id: int, base_currency: str = "USD") -> dict[str, Any]:
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


def buy_currency(user_id: int, currency_code: str, amount: float) -> dict[str, Any]:
    code = (currency_code or "").strip().upper()
    if not code:
        raise DomainError("currency_code не может быть пустым")
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
    # Will raise DomainError on insufficient funds
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


def sell_currency(user_id: int, currency_code: str, amount: float) -> dict[str, Any]:
    code = (currency_code or "").strip().upper()
    if not code:
        raise DomainError("currency_code не может быть пустым")
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
        raise DomainError(
            (
                "Недостаточно средств: доступно "
                f"{bal:.4f} {code}, требуется {amt:.4f} {code}"
            )
        )

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

