"""CLI entrypoint for ValutaTrade Hub.

Единственная точка входа для пользовательских команд. Здесь
только разбор аргументов и вывод. Вся логика — в core.usecases.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from typing import Any

from prettytable import PrettyTable

from ..core import usecases as uc


def _print_error(msg: str) -> None:
    print(msg)


def _print_portfolio(username: str, data: dict[str, Any]) -> None:
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
    for w in data["wallets"]:
        code = w.get("currency", "")
        bal = float(w.get("balance", 0.0))
        value = float(w.get("value", 0.0))
        rate = w.get("rate")
        updated = w.get("updated_at", "")
        rate_s = f"{float(rate):.6f}" if isinstance(rate, (int, float)) else ""
        table.add_row([f"{code}", f"{bal:.4f}", f"{value:.2f}", rate_s, updated])
    print(table)
    print("-" * 33)
    print(f"ИТОГО: {data['total']:.2f} {base}")


def build_parser() -> argparse.ArgumentParser:
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

    # get-rate
    p = sub.add_parser("get-rate", help="Получить курс")
    p.add_argument("--from", dest="frm", required=True)
    p.add_argument("--to", dest="to", required=True)

    return parser


def _run_once(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
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
            res = uc.buy_currency(sess["user_id"], ns.currency, ns.amount)
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
            res = uc.sell_currency(sess["user_id"], ns.currency, ns.amount)
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

        parser.print_help()
        return 2
    except uc.DomainError as exc:  # type: ignore[attr-defined]
        _print_error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        _print_error(f"Ошибка: {exc}")
        return 1


def _print_repl_help() -> None:
    print(
        "Доступные команды: register, login, show-portfolio, buy, sell, get-rate, "
        "help, exit"
    )
    print("Примеры:")
    print("  login --username ivan.petrov --password test1234")
    print("  show-portfolio --base USD")
    print("  buy --currency EUR --amount 1")
    print("  get-rate --from EUR --to USD")


def _repl_loop() -> int:
    print("ValutaTrade Hub REPL. Введите 'help' для подсказки, 'exit' для выхода.")
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
        code = _run_once(args)
        # Не выходим из REPL при ошибке — продолжаем
        if code == 0:
            continue
    # недостижимо
    # return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        return _repl_loop()
    return _run_once(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
