"""Сценарий C-15 «Жалоба»."""

from __future__ import annotations

from app.schemas.mis import EscalationCreate
from app.services.dialog.base import ScenarioProtocol
from app.services.dialog.state import DialogResponse, DialogState, STEP_ASK_NAME
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance
from app.services.transfer import TransferCard


class ComplaintScenario(ScenarioProtocol):
    name = "complaint"

    def __init__(self, mis: MISClientProtocol) -> None:
        self._mis = mis

    async def handle(
        self,
        state: DialogState,
        parsed: ParsedUtterance | None = None,
        red_flag=None,
        raw_text: str = "",
    ) -> DialogResponse:
        
        # Если пациент уже идентифицирован, создаём эскалацию
        if state.client_id:
            try:
                card = TransferCard(
                    call_id=state.call_id,
                    started_at=state.started_at,
                    transferred_at="",
                    intent="I-12 Жалоба",
                    reason_code="R-03",
                    reason_text=f"Жалоба пациента: {raw_text}",
                    priority="P2",
                    summary="Жалоба пациента",
                )
                await self._mis.create_escalation(
                    EscalationCreate(
                        client_id=state.client_id,
                        description=card.to_escalation_description(),
                    )
                )
            except Exception:
                pass # Если МИС упала, всё равно переводим

        state.step = "escalated"

        return DialogResponse(
            reply=(
                "Мне жаль, что так вышло. Соединяю вас со старшим администратором. "
                "Суть обращения уже передана, повторять не придётся. "
                "Оставайтесь на линии, пожалуйста."
            ),
            step=state.step,
            escalated=True,
        )