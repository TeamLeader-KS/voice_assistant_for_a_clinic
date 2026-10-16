"""Pydantic-схемы под REST API тестового стенда «Регистратура».

Источник контракта: https://crm-med-mock.dbi-testing.ru/docs/openapi.json

Особенности, зафиксированные в схемах:
    - Даты — строки «ДД.ММ.ГГГГ», дата-время — «ДД.ММ.ГГГГ ЧЧ:ММ» (GMT+4, без смещения).
    - Регистрация клиента при повторе ключа возвращает 200, а не 201.
    - Поля «middle_name» и «comment» могут быть null.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────
# Ошибки
# ─────────────────────────────────────────────────────────────


class MISErrorCode(str, Enum):
    """Машиночитаемые коды ошибок стенда."""

    UNAUTHORIZED = "НЕ_АВТОРИЗОВАН"
    INVALID_PARAM = "НЕВЕРНЫЙ_ПАРАМЕТР"
    INVALID_REQUEST = "НЕВЕРНЫЙ_ЗАПРОС"
    NOT_FOUND = "НЕ_НАЙДЕНО"
    STATUS_CONFLICT = "КОНФЛИКТ_СТАТУСА"
    RATE_LIMITED = "ПРЕВЫШЕН_ЛИМИТ"
    INTERNAL_ERROR = "ВНУТРЕННЯЯ_ОШИБКА"


class MISErrorBody(BaseModel):
    """Тело ответа об ошибке от стенда."""

    code: MISErrorCode
    message: str


# ─────────────────────────────────────────────────────────────
# Врачи
# ─────────────────────────────────────────────────────────────


class Doctor(BaseModel):
    """Врач справочника стенда."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., ge=1)
    full_name: str
    specialty: str
    is_active: bool


# ─────────────────────────────────────────────────────────────
# Клиенты
# ─────────────────────────────────────────────────────────────


class Client(BaseModel):
    """Карточка клиента команды."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., ge=1)
    last_name: str
    first_name: str
    middle_name: str | None = None
    birth_date: str
    comment: str | None = None
    created_at: str


class ClientCreate(BaseModel):
    """Тело регистрации клиента."""

    model_config = ConfigDict(extra="ignore")

    last_name: str = Field(..., min_length=1, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=100)
    birth_date: str
    middle_name: str | None = None
    comment: str | None = None


class ClientUpdate(BaseModel):
    """Тело изменения клиента (только отчество и комментарий)."""

    model_config = ConfigDict(extra="ignore")

    middle_name: str | None = None
    comment: str | None = None


# ─────────────────────────────────────────────────────────────
# Записи на приём
# ─────────────────────────────────────────────────────────────


class VisitStatus(str, Enum):
    """Статусы записи на приём."""

    PLANNED = "Запланирована"
    CANCELLED = "Отменена"
    COMPLETED = "Завершена"


class Visit(BaseModel):
    """Карточка записи на приём."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., ge=1)
    client_id: int = Field(..., ge=1)
    doctor: Doctor
    scheduled_at: str
    status: VisitStatus
    created_at: str
    updated_at: str


class VisitCreate(BaseModel):
    """Тело создания записи на приём."""

    model_config = ConfigDict(extra="ignore")

    client_id: int = Field(..., ge=1)
    doctor_id: int = Field(..., ge=1)
    scheduled_at: str


class VisitUpdate(BaseModel):
    """Тело изменения записи: перенос, смена врача, отмена, завершение.

    Все поля опциональны. Отсутствующее поле остаётся прежним.
    """

    model_config = ConfigDict(extra="ignore")

    doctor_id: int | None = Field(default=None, ge=1)
    scheduled_at: str | None = None
    status: VisitStatus | None = None


# ─────────────────────────────────────────────────────────────
# Заявки на соединение со специалистом
# ─────────────────────────────────────────────────────────────


class Escalation(BaseModel):
    """Карточка заявки на соединение со специалистом."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., ge=1)
    client_id: int = Field(..., ge=1)
    description: str
    created_at: str


class EscalationCreate(BaseModel):
    """Тело создания заявки на соединение со специалистом."""

    model_config = ConfigDict(extra="ignore")

    client_id: int = Field(..., ge=1)
    description: str = Field(..., min_length=1, max_length=1000)