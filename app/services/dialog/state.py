"""Состояние диалога и ответы ассистента."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.red_flags import RedFlag
from app.services.schedule import Slot

# Шаги
STEP_GREETING = "greeting"
STEP_ASK_NAME = "ask_name"
STEP_ASK_SPECIALTY = "ask_specialty"
STEP_OFFER_SLOTS = "offer_slots"
STEP_CONFIRM = "confirm"
STEP_BOOKED = "booked"
STEP_FALLBACK = "fallback"
STEP_ESCALATED = "escalated"


@dataclass
class DialogState:
    """Состояние диалога по одному звонку."""

    call_id: str
    scenario: str | None = None  # "booking" / "emergency"
    step: str = STEP_GREETING

    # Данные пациента
    last_name: str | None = None
    first_name: str | None = None
    birth_date: str | None = None
    full_name: str | None = None
    client_id: int | None = None

    # Запись
    specialty: str | None = None
    offered_slots: list[Slot] = field(default_factory=list)
    selected_slot: Slot | None = None
    visit_id: int | None = None

    # Служебные
    started_at: str = field(
        default_factory=lambda: datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    )
    red_flag: RedFlag | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogResponse:
    """Ответ ассистента."""

    reply: str
    step: str
    visit_id: int | None = None
    booked: bool = False
    escalated: bool = False
    red_flag_category: str | None = None