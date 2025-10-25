class InsufficientFundsError(Exception):
    """Недостаточно средств для операции."""

    def __init__(self, available: float, required: float, code: str) -> None:
        self.available = float(available)
        self.required = float(required)
        self.code = (code or "").upper()
        super().__init__(
            f"Недостаточно средств: доступно {self.available} {self.code}, "
            f"требуется {self.required} {self.code}"
        )


class CurrencyNotFoundError(Exception):
    """Неизвестная валюта."""

    def __init__(self, code: str) -> None:
        self.code = (code or "").upper()
        super().__init__(f"Неизвестная валюта '{self.code}'")


class ApiRequestError(Exception):
    """Ошибка при обращении к внешнему API (или обновлению курсов)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
