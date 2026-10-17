"""Роутер диалогового движка. Делегирует сценариям."""

from __future__ import annotations

from app.services.dialog.scenarios.booking import BookingScenario
from app.services.dialog.scenarios.cancel import CancelScenario
from app.services.dialog.scenarios.check import CheckScenario
from app.services.dialog.scenarios.emergency import EmergencyScenario
from app.services.dialog.state import (
    DialogResponse,
    DialogState,
    STEP_BOOKED,
    STEP_ESCALATED,
    STEP_GREETING,
)
from app.services.mis_client import MISClientProtocol
from app.services.nlu import parse
from app.services.red_flags import detect as detect_red_flag
from app.services.schedule import ScheduleService
from app.services.dialog.scenarios.complaint import ComplaintScenario


class DialogEngine:
    """Диалоговый движок — роутер по сценариям."""

    def __init__(
        self,
        mis: MISClientProtocol,
        schedule: ScheduleService,
        today: str,
    ) -> None:
        self._mis = mis
        self._schedule = schedule
        self._today = today
        self._states: dict[str, DialogState] = {}

        # Регистрация всех доступных сценариев
        self._scenarios = {
            "booking": BookingScenario(mis=mis, schedule=schedule),
            "emergency": EmergencyScenario(mis=mis),
            "cancel": CancelScenario(mis=mis),
            "check": CheckScenario(mis=mis),
            "complaint": ComplaintScenario(mis=mis),
        }

    def _get_state(self, call_id: str) -> DialogState:
        if call_id not in self._states:
            self._states[call_id] = DialogState(call_id=call_id)
        return self._states[call_id]

    def end_call(self, call_id: str) -> None:
        """Очистить состояние после завершения звонка (вызывается из voice)."""
        self._states.pop(call_id, None)

    async def handle(self, call_id: str, text: str) -> DialogResponse:
        """Обработать реплику пациента."""
        state = self._get_state(call_id)

        # 1. Красные флаги — ВСЕГДА первыми
        red_flag = detect_red_flag(text)
        if red_flag is not None:
            state.scenario = "emergency"
            return await self._scenarios["emergency"].handle(
                state, parsed=None, red_flag=red_flag, raw_text=text
            )

        # 2. Терминальные состояния (сброс при новом интенте)
        if state.step in (STEP_BOOKED, STEP_ESCALATED):
            parsed = await parse(text, self._today)
            
            # Если пациент хочет продолжить (новый интент)
            if parsed.intent in ("book", "cancel", "check"):
                state.scenario = None
                state.step = STEP_GREETING
                state.visit_id = None
                state.selected_slot = None
                state.offered_slots = []
                state.client_id = None
                state.last_name = None
                state.first_name = None
                state.birth_date = None
                state.full_name = None
            else:
                return DialogResponse(
                    reply="Хорошо. Всего доброго, будьте здоровы!",
                    step=state.step,
                )
        else:
            # 3. NLU (если диалог не терминальный)
            parsed = await parse(text, self._today)

        # 4. Выбираем сценарий по интенту
        if state.scenario is None:
            if parsed.intent == "cancel":
                state.scenario = "cancel"
            elif parsed.intent == "check":
                state.scenario = "check"
            elif parsed.intent == "complaint":
                state.scenario = "complaint"
            else:
                state.scenario = "booking"
            state.step = STEP_GREETING

        # 5. Делегируем в сценарий
        scenario = self._scenarios.get(state.scenario, self._scenarios["booking"])
        return await scenario.handle(
            state, parsed=parsed, raw_text=text
        )