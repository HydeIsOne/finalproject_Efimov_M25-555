"""CLI entrypoint (skeleton) for ValutaTrade Hub.

Полная логика команд будет добавлена в следующих этапах.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Skeleton CLI entrypoint.

    Args:
        argv: optional list of arguments; defaults to sys.argv[1:].
    Returns:
        Process exit code.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    print("ValutaTrade Hub CLI — скелет. Функциональность будет добавлена позже.")
    if args:
        print(f"Получены аргументы: {args}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
