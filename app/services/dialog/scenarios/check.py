"""Сценарий C-05 «Проверка своей записи»."""

from __future__ import annotations

from app.schemas.mis import VisitStatus
from app.services.dialog.base import ScenarioProtocol
from app.services.dialog.state import DialogResponse, DialogState, STEP_ASK_NAME, STEP_BOOKED
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance

STEP_CHECK_RESULT = "check_result"


class CheckScenario(ScenarioProtocol):
    name = "check"

    def __init__(self, mis: MISClientProtocol) -> None:
        self._mis = mis

    async def handle(self, state: DialogState, parsed: ParsedUtterance | None = None, red_flag=None, raw_text: str = "") -> DialogResponse:
        if state.step in ("greeting", STEP_ASK_NAME):
            return await self._handle_name(state, parsed)
        if state.step == STEP_CHECK_RESULT:
            state.step = STEP_BOOKED
            return DialogResponse(reply="Рад был помочь. Что-нибудь ещё?", step=state.step)

        state.step = "greeting"
        return DialogResponse(reply="Извините, я не понял. Назовите фамилию, имя, отчество и дату рождения.", step=state.step)

    async def _handle_name(self, state: DialogState, parsed: ParsedUtterance | None) -> DialogResponse:
        if not parsed or not (parsed.last_name and parsed.first_name and parsed.birth_date):
            state.step = STEP_ASK_NAME
            return DialogResponse(reply="Назовите, пожалуйста, фамилию, имя, отчество и дату рождения.", step=state.step)

        state.last_name = parsed.last_name
        state.first_name = parsed.first_name
        state.middle_name = parsed.middle_name
        state.birth_date = parsed.birth_date
        state.full_name = f"{parsed.last_name} {parsed.first_name}"

        try:
            clients = await self._mis.find_clients(last_name=state.last_name, first_name=state.first_name, birth_date=state.birth_date)
        except Exception:
            clients = []

        if not clients:
            state.step = STEP_BOOKED
            return DialogResponse(reply="Я не нашёл вас в базе.", step=state.step)

        client = clients[0]
        visits = await self._mis.list_visits(client_id=client.id, status=VisitStatus.PLANNED)
        state.step = STEP_CHECK_RESULT

        if not visits:
            return DialogResponse(reply="У вас нет активных записей.", step=state.step)

        if len(visits) == 1:
            reply = f"Вы записаны на {visits[0].scheduled_at} к {visits[0].doctor.full_name}. Возьмите с собой паспорт и полис. Могу ещё чем-то помочь?"
        else:
            lines = [f"{i}. {v.scheduled_at} к {v.doctor.full_name}" for i, v in enumerate(visits, 1)]
            options = "\n".join(lines)
            reply = f"У вас несколько записей:\n{options}\nВозьмите с собой паспорт и полис. Могу ещё чем-то помочь?"

        return DialogResponse(reply=reply, step=state.step)