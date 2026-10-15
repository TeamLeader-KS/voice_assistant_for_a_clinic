from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    String, Integer, DateTime, Enum as SAEnum,
    CheckConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CallResult(str, PyEnum):
    MISSED = "пропущен"
    TRANSFER = "перевод"
    REFERENCE = "справка"
    BOOKED = "записан"


class CallLog(Base):
    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        comment="Идентификатор звонка, напр. C000001",
    )
    datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Момент звонка",
    )
    wait_sec: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Время ожидания в секундах",
    )
    duration_sec: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Длительность разговора в секундах",
    )
    result: Mapped[CallResult] = mapped_column(
        SAEnum(
            CallResult,
            name="call_result_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
        comment="Результат звонка",
    )
    operator_ext: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Добавочный номер оператора; 0 — оператор не участвовал",
    )
    caller_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Реальный номер вызывающего абонента в формате E.164, напр. +79291234580",
    )

    __table_args__ = (
        CheckConstraint("wait_sec >= 0", name="ck_calls_wait_sec_nonneg"),
        CheckConstraint("duration_sec >= 0", name="ck_calls_duration_sec_nonneg"),
        CheckConstraint("operator_ext >= 0", name="ck_calls_operator_ext_nonneg"),

        CheckConstraint(
            "(result <> 'пропущен') "
            "OR (wait_sec = 0 AND duration_sec = 0 AND operator_ext = 0)",
            name="ck_calls_missed_consistency",
        ),

        # реальный номер в E.164: + и 10..15 цифр
        CheckConstraint(
            r"caller_number ~ '^\+[1-9][0-9]{9,14}$'",
            name="ck_calls_caller_number_e164",
        ),

        Index("ix_calls_result_datetime", "result", "datetime"),
    )

    def __repr__(self) -> str:
        return (
            f"<Call(call_id={self.call_id!r}, "
            f"result={self.result.value!r}, dt={self.datetime:%Y-%m-%d %H:%M:%S})>"
        )