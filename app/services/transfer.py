"""Карточка перевода на оператора (Приложение В регламента РГ-ТЕЛ-01).

Формируется ГА при эскалации и передаётся регистратору вместе со звонком.
Также используется для задач обратного звонка.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TransferCard:
    """Карточка перевода (Приложение В)."""

    call_id: str
    started_at: str
    transferred_at: str
    patient_id: int | None = None
    patient_name: str | None = None
    intent: str = ""
    collected_params: dict = field(default_factory=dict)
    reason_code: str = ""        # например, "R-01", "R-11"
    reason_text: str = ""        # человекочитаемое описание
    priority: str = "P3"          # P1 / P2 / P3
    summary: str = ""             # до 200 символов
    is_dissatisfied: bool = False
    recording_consent: bool = True

    def to_escalation_description(self) -> str:
        """Текст описания для MIS-эскалации.

        Максимум 1000 символов (ограничение стенда).
        """
        parts: list[str] = []

        if self.reason_code:
            parts.append(f"[{self.reason_code}]")
        if self.priority:
            parts.append(f"Приоритет: {self.priority}.")

        if self.reason_text:
            parts.append(self.reason_text)

        if self.patient_name:
            parts.append(f"Пациент: {self.patient_name}.")

        if self.collected_params:
            params = ", ".join(f"{k}={v}" for k, v in self.collected_params.items())
            parts.append(f"Параметры: {params}.")

        if self.summary:
            parts.append(f"Резюме: {self.summary}")

        text = " ".join(parts)
        return text[:1000]


def build_emergency_card(
    call_id: str,
    started_at: str,
    red_flag_group: str,
    matched: str,
    patient_name: str | None = None,
    patient_id: int | None = None,
) -> TransferCard:
    """Построить карточку для экстренной ситуации (R-01)."""
    return TransferCard(
        call_id=call_id,
        started_at=started_at,
        transferred_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        patient_id=patient_id,
        patient_name=patient_name,
        intent="I-11 Экстренная ситуация",
        reason_code="R-01",
        reason_text=(
            f"Красный флаг категории А: {red_flag_group}. "
            f"Сработало: «{matched}». Рекомендовано 103/112."
        ),
        priority="P1",
        summary=f"Экстренный: {red_flag_group}",
    )


def build_urgent_card(
    call_id: str,
    started_at: str,
    red_flag_group: str,
    matched: str,
    patient_name: str | None = None,
    patient_id: int | None = None,
) -> TransferCard:
    """Построить карточку для острого состояния (R-11)."""
    return TransferCard(
        call_id=call_id,
        started_at=started_at,
        transferred_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        patient_id=patient_id,
        patient_name=patient_name,
        intent="I-11 Острое состояние",
        reason_code="R-11",
        reason_text=(
            f"Красный флаг категории Б: {red_flag_group}. "
            f"Сработало: «{matched}»."
        ),
        priority="P1",
        summary=f"Острое состояние: {red_flag_group}",
    )