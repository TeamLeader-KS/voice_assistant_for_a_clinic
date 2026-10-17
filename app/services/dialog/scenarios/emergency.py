"""Сценарий C-14 «Экстренная ситуация»."""

from __future__ import annotations

from app.core.constants import RED_FLAG_CATEGORY_A
from app.schemas.mis import EscalationCreate
from app.services.dialog.base import ScenarioProtocol
from app.services.dialog.state import (
    DialogResponse,
    DialogState,
    STEP_ESCALATED,
)
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance
from app.services.red_flags import RedFlag
from app.services.transfer import build_emergency_card, build_urgent_card


class EmergencyScenario(ScenarioProtocol):
    name = "emergency"

    def __init__(self, mis: MISClientProtocol) -> None:
        self._mis = mis

    async def handle(
        self,
        state: DialogState,
        parsed: ParsedUtterance | None = None,
        red_flag: RedFlag | None = None,
        raw_text: str = "",
    ) -> DialogResponse:
        if red_flag is None:
            # Если сюда попали без флага — возвращаем на всякий случай
            return DialogResponse(
                reply="Соединяю вас с сотрудником.",
                step=STEP_ESCALATED,
                escalated=True,
            )

        if not state.full_name and state.last_name and state.first_name:
            state.full_name = f"{state.last_name} {state.first_name}"

        if red_flag.category == RED_FLAG_CATEGORY_A:
            card = build_emergency_card(
                call_id=state.call_id,
                started_at=state.started_at,
                red_flag_group=red_flag.group,
                matched=red_flag.matched,
                patient_name=state.full_name,
                patient_id=state.client_id,
            )
        else:
            card = build_urgent_card(
                call_id=state.call_id,
                started_at=state.started_at,
                red_flag_group=red_flag.group,
                matched=red_flag.matched,
                patient_name=state.full_name,
                patient_id=state.client_id,
            )

        if state.client_id is not None:
            try:
                await self._mis.create_escalation(
                    EscalationCreate(
                        client_id=state.client_id,
                        description=card.to_escalation_description(),
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        state.step = STEP_ESCALATED
        state.red_flag = red_flag

        return DialogResponse(
            reply=red_flag.phrase,
            step=state.step,
            escalated=True,
            red_flag_category=red_flag.category,
        )