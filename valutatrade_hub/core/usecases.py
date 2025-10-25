"""Business use-cases for ValutaTrade Hub.

Реализация сценариев (регистрация, операции кошелька,
сделки, история) будет добавлена позже.
"""

from __future__ import annotations


class UseCaseNotImplementedError(Exception):
    """Raised when a use-case is not yet implemented."""
