"""Кастомные исключения приложения.

Иерархия:
    AppError
    ├── MISError                    — общий предок ошибок MIS-клиента
    │   ├── MISUnauthorized         — 401, недействительный токен
    │   ├── MISValidationError      — 400, неверные данные запроса
    │   ├── MISNotFound             — 404, объект не найден
    │   ├── MISConflict             — 409, недопустимое изменение
    │   ├── MISRateLimited          — 429, превышен лимит запросов
    │   └── MISServerError          — 500, неисправность стенда
    └── DialogError                 — ошибки диалогового движка
"""

from __future__ import annotations


class AppError(Exception):
    """Базовое исключение приложения."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


# ─────────────────────────────────────────────────────────────
# MIS — интеграция со стендом «Регистратура»
# ─────────────────────────────────────────────────────────────


class MISError(AppError):
    """Базовая ошибка MIS-клиента.

    Атрибуты:
        code: машиночитаемый код из ответа стенда (например, «НЕ_НАЙДЕНО»).
        status_code: HTTP-статус ответа стенда.
        message: описание на русском языке из поля «message».
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class MISUnauthorized(MISError):
    """401 — токен команды не предъявлен, неизвестен или отозван."""


class MISValidationError(MISError):
    """400 — неверные данные запроса или недопустимый параметр."""


class MISNotFound(MISError):
    """404 — запрошенный объект или метод не существует."""


class MISConflict(MISError):
    """409 — состояние объекта изменения не допускает."""


class MISRateLimited(MISError):
    """429 — исчерпан предел частоты запросов.

    Атрибут retry_after — число секунд из заголовка «Retry-After».
    """

    def __init__(
        self,
        message: str = "",
        *,
        retry_after: int | None = None,
        code: str | None = None,
        status_code: int | None = 429,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, code=code, status_code=status_code)


class MISServerError(MISError):
    """500 — неисправность стенда или исход, не выразимый прочими кодами."""


# ─────────────────────────────────────────────────────────────
# Диалоговый движок
# ─────────────────────────────────────────────────────────────


class DialogError(AppError):
    """Базовая ошибка диалогового движка."""


class RedFlagDetected(DialogError):
    """Обнаружен красный флаг — требуется немедленная эскалация.

    Атрибут category — категория из раздела 7.4 регламента.
    """

    def __init__(self, message: str = "", *, category: str | None = None) -> None:
        self.category = category
        super().__init__(message)