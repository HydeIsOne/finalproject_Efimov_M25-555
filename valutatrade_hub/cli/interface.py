"""CLI entrypoint for ValutaTrade Hub.

Единственная точка входа для пользовательских команд. Здесь
только разбор аргументов и вывод. Вся логика — в core.usecases.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from datetime import datetime
from typing import Any

from prettytable import PrettyTable

from ..core import currencies as cur
from ..core import usecases as uc
from ..core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from ..logging_config import configure_logging
from ..parser_service.scheduler import (
    maybe_auto_update_on_start as _maybe_auto_update,
)


def _print_error(msg: str) -> None:
    """Print a user-facing error message (no stack traces)."""
    print(msg)




def _print_portfolio(username: str, data: dict[str, Any]) -> None:
    """Render portfolio summary table.

    Args:
        username: Display name for header.
        data: Result of usecases.show_portfolio.
    """
    base = data["base"]
    print(f"Портфель пользователя '{username}' (база: {base}):")
    table = PrettyTable()
    table.field_names = [
        "Валюта",
        "Баланс",
        f"Стоимость ({base})",
        "Курс",
        "Обновлено",
    ]
    # Align numeric columns to the right for better readability
    table.align["Валюта"] = "l"
    table.align["Баланс"] = "r"
    table.align[f"Стоимость ({base})"] = "r"
    table.align["Курс"] = "r"
    table.align["Обновлено"] = "l"
    for w in data["wallets"]:
        code = w.get("currency", "")
        bal = float(w.get("balance", 0.0))
        value = float(w.get("value", 0.0))
        rate = w.get("rate")
        updated = w.get("updated_at", "")
        # Normalize timestamp to seconds for consistent display
        updated_s = updated
        if isinstance(updated, str) and updated:
            try:
                dt = datetime.fromisoformat(updated)
                updated_s = dt.replace(microsecond=0).isoformat()
            except Exception:  # noqa: BLE001
                updated_s = updated
        rate_s = f"{float(rate):.6f}" if isinstance(rate, (int, float)) else ""
        # Use thousands separators for balances and values
        table.add_row([
            f"{code}",
            f"{bal:,.4f}",
            f"{value:,.2f}",
            rate_s,
            updated_s,
        ])
    # Summary row
    table.add_row([
        "ИТОГО",
        "",
        f"{data['total']:,.2f}",
        "",
        "",
    ])
    print(table)
    print("-" * 33)
    print(f"ИТОГО: {data['total']:,.2f} {base}")


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="valutatrade")
    sub = parser.add_subparsers(dest="command", required=True)

    # register
    p = sub.add_parser("register", help="Создать пользователя")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)

    # login
    p = sub.add_parser("login", help="Войти в систему")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)

    # show-portfolio
    p = sub.add_parser("show-portfolio", help="Показать портфель")
    p.add_argument("--base", default="USD")

    # buy
    p = sub.add_parser("buy", help="Купить валюту")
    p.add_argument("--currency", required=True)
    p.add_argument("--amount", required=True, type=float)

    # sell
    p = sub.add_parser("sell", help="Продать валюту")
    p.add_argument("--currency", required=True)
    p.add_argument("--amount", required=True, type=float)

    # deposit
    p = sub.add_parser("deposit", help="Пополнить кошелёк (по умолчанию USD)")
    p.add_argument("--currency", default="USD", help="Код валюты (по умолчанию USD)")
    p.add_argument("--amount", required=True, type=float)

    # withdraw
    p = sub.add_parser("withdraw", help="Снять средства с кошелька (по умолчанию USD)")
    p.add_argument("--currency", default="USD", help="Код валюты (по умолчанию USD)")
    p.add_argument("--amount", required=True, type=float)

    # get-rate
    p = sub.add_parser("get-rate", help="Получить курс")
    p.add_argument("--from", dest="frm", required=True)
    p.add_argument("--to", dest="to", required=True)

    # list-currencies
    sub.add_parser("list-currencies", help="Список поддерживаемых валют")

    # clear-history
    sub.add_parser(
        "clear-history",
        help="Очистить историю курсов (data/exchange_rates.json)",
    )

    # update-rates (Parser Service)
    p = sub.add_parser("update-rates", help="Обновить курсы из внешних API")
    p.add_argument(
        "--source",
        choices=["coingecko", "exchangerate"],
        help="Обновить данные только из указанного источника",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Записывать снимок кэша строго из текущего обновления (без слияния с"
            " предыдущими парами)"
        ),
    )
    p.add_argument(
        "--all-fiat",
        action="store_true",
        help=(
            "Загружать все доступные фиатные валюты из ExchangeRate-API (по умолчанию"
            " только EUR, GBP, RUB)"
        ),
    )
    p.add_argument(
        "--no-history",
        action="store_true",
        help=(
            "Не записывать новые записи в историю (exchange_rates.json) во время"
            " этого обновления"
        ),
    )

    # show-rates
    p = sub.add_parser("show-rates", help="Показать актуальные курсы из кеша")
    p.add_argument("--currency", help="Фильтр по валюте (например, BTC)")
    p.add_argument("--top", type=int, help="Показать N самых дорогих криптовалют")
    p.add_argument("--base", help="База для отображения (по умолчанию USD)")

    # schedule (Parser Service)
    p = sub.add_parser("schedule", help="Периодическое обновление курсов")
    p.add_argument(
        "--interval",
        type=float,
        default=300.0,
        help="Интервал обновления в секундах (по умолчанию 300)",
    )
    p.add_argument(
        "--source",
        choices=["coingecko", "exchangerate"],
        help="Обновлять только из указанного источника",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Записывать снимок кэша строго из текущего обновления (без слияния с"
            " предыдущими парами)"
        ),
    )
    p.add_argument(
        "--all-fiat",
        action="store_true",
        help=(
            "Загружать все доступные фиатные валюты из ExchangeRate-API (по умолчанию"
            " только EUR, GBP, RUB)"
        ),
    )
    p.add_argument(
        "--no-history",
        action="store_true",
        help=(
            "Не записывать новые записи в историю (exchange_rates.json) во время"
            " этого обновления"
        ),
    )

    return parser


def _run_once(argv: list[str]) -> int:
    """Execute a single CLI command and return process exit code."""
    parser = build_parser()
    ns = parser.parse_args(argv)
    # Best-effort daily auto-update on first command
    # (unless user runs update explicitly)
    _maybe_auto_update(ns.command)
    try:
        if ns.command == "register":
            res = uc.register_user(ns.username, ns.password)
            print(
                (
                    f"Пользователь '{res['username']}' зарегистрирован "
                    f"(id={res['user_id']}). "
                    f"Войдите: login --username {res['username']} --password ****"
                )
            )
            return 0

        if ns.command == "login":
            res = uc.login_user(ns.username, ns.password)
            print(f"Вы вошли как '{res['username']}'")
            return 0

        if ns.command == "show-portfolio":
            sess = uc.require_login()
            data = uc.show_portfolio(sess["user_id"], base_currency=ns.base)
            _print_portfolio(sess["username"], data)
            return 0

        if ns.command == "buy":
            sess = uc.require_login()
            res = uc.buy_currency(
                sess["user_id"], ns.currency, ns.amount, username=sess["username"]
            )
            print(
                (
                    "Покупка выполнена: "
                    f"{res['amount']:.4f} {res['currency']} по курсу "
                    f"{res['rate_usd']:.2f} USD/{res['currency']}"
                )
            )
            print(
                "Изменения в портфеле:\n"
                f"- {res['currency']}: стало {res['new_balance']:.4f}"
            )
            print(f"Оценочная стоимость покупки: {res['cost_usd']:.2f} USD")
            return 0

        if ns.command == "sell":
            sess = uc.require_login()
            res = uc.sell_currency(
                sess["user_id"], ns.currency, ns.amount, username=sess["username"]
            )
            print(
                (
                    "Продажа выполнена: "
                    f"{res['amount']:.4f} {res['currency']} по курсу "
                    f"{res['rate_usd']:.2f} USD/{res['currency']}"
                )
            )
            print(
                "Изменения в портфеле:\n"
                f"- {res['currency']}: стало {res['new_balance']:.4f}"
            )
            print(f"Оценочная выручка: {res['proceeds_usd']:.2f} USD")
            return 0

        if ns.command == "deposit":
            sess = uc.require_login()
            code = (ns.currency or "USD").upper()
            amt = float(ns.amount)
            if amt <= 0:
                _print_error("'amount' должен быть положительным числом")
                return 1
            uc.add_currency(sess["user_id"], code)
            new_wallet = uc.adjust_wallet(sess["user_id"], code, amt)
            print(
                (
                    f"Пополнение: +{amt:.4f} {code}. Баланс: "
                    f"{new_wallet['balance']:.4f} {code}"
                )
            )
            return 0

        if ns.command == "withdraw":
            sess = uc.require_login()
            code = (ns.currency or "USD").upper()
            amt = float(ns.amount)
            if amt <= 0:
                _print_error("'amount' должен быть положительным числом")
                return 1
            try:
                new_wallet = uc.adjust_wallet(sess["user_id"], code, -amt)
            except uc.DomainError as exc:  # type: ignore[attr-defined]
                _print_error(str(exc))
                return 1
            print(
                f"Снятие: -{amt:.4f} {code}. Баланс: {new_wallet['balance']:.4f} {code}"
            )
            return 0

        if ns.command == "get-rate":
            info = uc.get_rate(ns.frm, ns.to)
            inv = uc.get_rate(ns.to, ns.frm)
            print(
                f"Курс {ns.frm.upper()}→{ns.to.upper()}: {info['rate']:.8f} "
                f"(обновлено: {info['updated_at']})"
            )
            print(
                f"Обратный курс {ns.to.upper()}→{ns.frm.upper()}: {inv['rate']:.8f}"
            )
            return 0

        if ns.command == "list-currencies":
            table = PrettyTable()
            table.field_names = ["Код", "Название", "Тип"]
            for c in cur.list_supported():
                kind = "FIAT" if c.__class__.__name__.startswith("Fiat") else "CRYPTO"
                table.add_row([c.code, getattr(c, "name", c.code), kind])
            print("Поддерживаемые валюты:")
            print(table)
            return 0

        if ns.command == "clear-history":
            from ..parser_service.storage import clear_history

            removed = clear_history()
            print(f"История очищена: удалено {removed} записей")
            return 0

        if ns.command == "update-rates":
            # Lazy import to avoid heavy deps during normal CLI usage
            from ..parser_service.updater import run_update

            # Enable strict snapshot mode for this run if requested
            prev_strict = os.environ.get("PARSER_SNAPSHOT_STRICT")
            prev_all_fiat = os.environ.get("PARSER_FIAT_ALL")
            prev_hist_off = os.environ.get("PARSER_HISTORY_DISABLED")
            if getattr(ns, "strict", False):
                os.environ["PARSER_SNAPSHOT_STRICT"] = "1"
            if getattr(ns, "all_fiat", False):
                os.environ["PARSER_FIAT_ALL"] = "1"
            if getattr(ns, "no_history", False):
                os.environ["PARSER_HISTORY_DISABLED"] = "1"
            summary = run_update(source=ns.source)
            # Restore env var
            if getattr(ns, "strict", False):
                if prev_strict is None:
                    os.environ.pop("PARSER_SNAPSHOT_STRICT", None)
                else:
                    os.environ["PARSER_SNAPSHOT_STRICT"] = prev_strict
            if getattr(ns, "all_fiat", False):
                if prev_all_fiat is None:
                    os.environ.pop("PARSER_FIAT_ALL", None)
                else:
                    os.environ["PARSER_FIAT_ALL"] = prev_all_fiat
            if getattr(ns, "no_history", False):
                if prev_hist_off is None:
                    os.environ.pop("PARSER_HISTORY_DISABLED", None)
                else:
                    os.environ["PARSER_HISTORY_DISABLED"] = prev_hist_off
            print(
                "Обновление выполнено: "
                f"fiat={summary['fiat']}, crypto={summary['crypto']}, "
                f"добавлено={summary['added']} записей"
            )
            return 0

        if ns.command == "show-rates":
            from ..parser_service.storage import read_snapshot

            def _parse_ts(s: str | None) -> datetime:
                if not s:
                    return datetime.min
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    return datetime.min

            snap = read_snapshot()
            pairs = dict(snap.get("pairs") or {})

            base = (
                (ns.base or "USD").strip().upper()
                if getattr(ns, "base", None)
                else "USD"
            )

            # Если база указана, покажем курсы вида CUR_BASE; иначе — как есть
            rows: list[tuple[str, float, str]] = []
            if base and base != "" and base != "USD":
                # Собираем множество доступных валют из левой части пар
                currencies: set[str] = set()
                for k in pairs.keys():
                    if "_" in k:
                        currencies.add(k.split("_", 1)[0])
                # В помощь расчёту найдём пары *_USD для отношения через USD
                def get_pair(name: str) -> tuple[float | None, str | None]:
                    obj = pairs.get(name)
                    if isinstance(obj, dict):
                        try:
                            return (
                                float(obj.get("rate", 0.0)),
                                str(obj.get("updated_at", "")),
                            )
                        except Exception:
                            return None, None
                    return None, None

                base_usd_rate, base_usd_ts = get_pair(f"{base}_USD")
                if base == "USD":
                    base_usd_rate = 1.0
                    base_usd_ts = snap.get("last_refresh")

                for cur_code in sorted(currencies):
                    if cur_code == base:
                        continue
                    # 1) Пробуем прямую пару CUR_BASE
                    r, ts = get_pair(f"{cur_code}_{base}")
                    if r is not None and r > 0:
                        rows.append((f"{cur_code}_{base}", r, ts or ""))
                        continue
                    # 2) Пытаемся через USD: CUR_USD / BASE_USD
                    cur_usd_rate, cur_usd_ts = get_pair(f"{cur_code}_USD")
                    if cur_usd_rate is not None and base_usd_rate and base_usd_rate > 0:
                        derived = cur_usd_rate / base_usd_rate
                        # Для метки времени возьмём минимально свежее из двух
                        ts_use = base_usd_ts or cur_usd_ts or ""
                        if base_usd_ts and cur_usd_ts:
                            ts_use = (
                                base_usd_ts
                                if _parse_ts(base_usd_ts) <= _parse_ts(cur_usd_ts)
                                else cur_usd_ts
                            )
                        rows.append((f"{cur_code}_{base}", derived, ts_use))

                # Фильтр по валюте
                if ns.currency:
                    pref = ns.currency.strip().upper() + "_"
                    rows = [r for r in rows if r[0].startswith(pref)]
            else:
                # База — USD (по умолчанию) или не указана:
                # показываем то, что есть в snapshot
                for k, v in pairs.items():
                    try:
                        rows.append(
                            (
                                k,
                                float(v.get("rate", 0.0)),
                                str(v.get("updated_at", "")),
                            )
                        )
                    except Exception:
                        continue
                if ns.currency:
                    pref = ns.currency.strip().upper() + "_"
                    rows = [r for r in rows if r[0].startswith(pref)]

            # Сортировки
            if ns.top:
                rows = sorted(rows, key=lambda x: x[1], reverse=True)[: max(0, ns.top)]
            else:
                rows = sorted(rows, key=lambda x: x[0])

            if not rows:
                print("Локальный кеш курсов пуст. Выполните 'update-rates'.")
                return 1

            print(
                f"Rates from cache (last_refresh: {snap.get('last_refresh', '')}):"
            )
            for name, rate, ts in rows:
                print(f"- {name}: {rate:.6f} (updated: {ts})")
            return 0

        if ns.command == "schedule":
            from ..parser_service.scheduler import run_periodic

            prev_strict = os.environ.get("PARSER_SNAPSHOT_STRICT")
            prev_all_fiat = os.environ.get("PARSER_FIAT_ALL")
            prev_hist_off = os.environ.get("PARSER_HISTORY_DISABLED")
            try:
                if getattr(ns, "strict", False):
                    os.environ["PARSER_SNAPSHOT_STRICT"] = "1"
                if getattr(ns, "all_fiat", False):
                    os.environ["PARSER_FIAT_ALL"] = "1"
                if getattr(ns, "no_history", False):
                    os.environ["PARSER_HISTORY_DISABLED"] = "1"
                print(
                    (
                        "Запуск периодического обновления. "
                        "Нажмите Ctrl+C для остановки.\n"
                        f"Интервал: {ns.interval:.1f} сек."
                        + (f", источник: {ns.source}" if ns.source else "")
                    )
                )
                run_periodic(interval_seconds=float(ns.interval), source=ns.source)
            except KeyboardInterrupt:
                # Graceful stop
                pass
            finally:
                # Restore env vars
                if getattr(ns, "strict", False):
                    if prev_strict is None:
                        os.environ.pop("PARSER_SNAPSHOT_STRICT", None)
                    else:
                        os.environ["PARSER_SNAPSHOT_STRICT"] = prev_strict
                if getattr(ns, "all_fiat", False):
                    if prev_all_fiat is None:
                        os.environ.pop("PARSER_FIAT_ALL", None)
                    else:
                        os.environ["PARSER_FIAT_ALL"] = prev_all_fiat
                if getattr(ns, "no_history", False):
                    if prev_hist_off is None:
                        os.environ.pop("PARSER_HISTORY_DISABLED", None)
                    else:
                        os.environ["PARSER_HISTORY_DISABLED"] = prev_hist_off
            return 0

        parser.print_help()
        return 2
    except InsufficientFundsError as exc:
        _print_error(str(exc))
        return 1
    except CurrencyNotFoundError as exc:
        _print_error(str(exc))
        _print_error("Подсказка: используйте get-rate или проверьте код валюты")
        return 1
    except ApiRequestError as exc:
        _print_error(str(exc))
        _print_error("Повторите попытку позже или проверьте сеть")
        return 1
    except uc.DomainError as exc:  # type: ignore[attr-defined]
        _print_error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        _print_error(f"Ошибка: {exc}")
        return 1


def _print_repl_help() -> None:
    """Print short help for REPL usage with examples."""
    print("Доступные команды:")
    print("  register --username <name> --password <pwd>")
    print("  login --username <name> --password <pwd>")
    print("  show-portfolio [--base USD]")
    print("  buy --currency <CODE> --amount <NUM>")
    print("  sell --currency <CODE> --amount <NUM>")
    print("  deposit [--currency USD] --amount <NUM>")
    print("  withdraw [--currency USD] --amount <NUM>")
    print("  get-rate --from <CODE> --to <CODE>")
    print("  list-currencies")
    print(
        "  update-rates [--source exchangerate|coingecko] [--strict] [--all-fiat] "
        "[--no-history]"
    )
    print("  clear-history   # очистить data/exchange_rates.json")
    print(
        "  show-rates [--currency <CODE>] [--top N] [--base <CODE>] "
        "# просмотр кеша"
    )
    print(
        "  schedule [--interval 300] [--source exchangerate|coingecko] [--strict] "
        "[--all-fiat] [--no-history]"
    )
    print("  help | exit")
    print("\nПримеры:")
    print("  login --username alice --password 1234")
    print("  update-rates --strict --no-history")
    print("  show-rates --base EUR --currency BTC")
    print("  schedule --interval 600 --strict")


def _repl_loop() -> int:
    """Run the interactive REPL loop until user exits."""
    # Best-effort daily auto-update at REPL start
    _maybe_auto_update(None)
    print(
        (
            "Вас приветствует ValutaTrade Hub — виртуальная платформа для "
            "отслеживания и симуляции торговли валютами.\n"
            "Введите 'help' для списка команд, 'exit' для выхода."
        )
    )
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            return 0
        if line.lower() in {"help", "?"}:
            _print_repl_help()
            continue
        try:
            args = shlex.split(line)
        except ValueError as exc:
            _print_error(f"Парсинг команды: {exc}")
            continue
        try:
            code = _run_once(args)
        except SystemExit:
            # Ошибки argparse (некорректные аргументы) не должны завершать REPL
            # Сообщение об ошибке уже напечатано argparse; просто продолжаем.
            # Дополнительно можно вывести код: str(exc)
            continue
        # Не выходим из REPL при ошибке — продолжаем
        if code == 0:
            continue
    # недостижимо
    # return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by Poetry script and main.py.

    Args:
        argv: Optional explicit argv (without program name). If None, uses sys.argv[1:].
    Returns:
        Exit code integer (0 success, non-zero on error).
    """
    # Ensure logging is configured once per process
    configure_logging()
    args = sys.argv[1:] if argv is None else argv
    if not args:
        return _repl_loop()
    return _run_once(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
