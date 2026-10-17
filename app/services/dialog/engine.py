"""Роутер диалогового движка. Делегирует сценариям."""

from __future__ import annotations

from app.services.dialog.scenarios.booking import BookingScenario
from app.services.dialog.scenarios.emergency import EmergencyScenario
from app.services.dialog.state import (
    DialogResponse,
    DialogState,
    STEP_ESCALATED,
    STEP_GREETING,
)
from app.services.mis_client import MISClientProtocol
from app.services.nlu import parse
from app.services.red_flags import detect as detect_red_flag
from app.services.schedule import ScheduleService


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

        self._scenarios = {
            "booking": BookingScenario(mis=mis, schedule=schedule),
            "emergency": EmergencyScenario(mis=mis),
        }

    def _get_state(self, call_id: str) -> DialogState:
        if call_id not in self._states:
            self._states[call_id] = DialogState(call_id=call_id)
        return self._states[call_id]

    async def handle(self, call_id: str, text: str) -> DialogResponse:
        """Обработать реплику пациента."""
        state = self._get_state(call_id)

        # 1. Красные флаги — ВСЕГДА первыми
        red_flag = detect_red_flag(text)
        if red_flag is not None:
            state.scenario = "emergency"
            return await self._scenarios["emergency"].handle(
                state, red_flag=red_flag, raw_text=text
            )

        # 2. Терминальные состояния — ничего не делаем
        if state.step == STEP_ESCALATED:
            return DialogResponse(
                reply=(
                    "Мы уже передали ваш вопрос сотруднику. "
                    "Оставайтесь на линии, пожалуйста."
                ),
                step=state.step,
                escalated=True,
                red_flag_category=(
                    state.red_flag.category if state.red_flag else None
                ),
            )

        # 3. NLU
        parsed = await parse(text, self._today)

        # 4. Если сценарий ещё не выбран — по умолчанию booking
        #    (в будущем здесь будет маршрутизация по intent)
        if state.scenario is None:
            state.scenario = "booking"
            state.step = STEP_GREETING

        # 5. Делегируем в сценарий
        scenario = self._scenarios.get(state.scenario, self._scenarios["booking"])
        return await scenario.handle(
            state, parsed=parsed, raw_text=text
        )