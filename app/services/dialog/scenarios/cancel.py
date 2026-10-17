"""Сценарий C-04 «Отмена записи»."""

from __future__ import annotations

from app.schemas.mis import VisitStatus, VisitUpdate
from app.services.dialog.base import ScenarioProtocol
from app.services.dialog.state import DialogResponse, DialogState, STEP_ASK_NAME, STEP_BOOKED
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance

STEP_CANCEL_LIST = "cancel_list"
STEP_CANCEL_CONFIRM = "cancel_confirm"


class CancelScenario(ScenarioProtocol):
    name = "cancel"

    def __init__(self, mis: MISClientProtocol) -> None:
        self._mis = mis

    async def handle(self, state: DialogState, parsed: ParsedUtterance | None = None, red_flag=None, raw_text: str = "") -> DialogResponse:
        if state.step in ("greeting", STEP_ASK_NAME):
            return await self._handle_name(state, parsed)
        if state.step == STEP_CANCEL_LIST:
            return await self._handle_list(state)
        if state.step == STEP_CANCEL_CONFIRM:
            return await self._handle_confirm(state, raw_text)
        if state.step == STEP_BOOKED:
            return DialogResponse(reply="Запись уже отменена. Хотите что-то ещё?", step=state.step)

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
        state.step = STEP_CANCEL_LIST
        return await self._handle_list(state)

    async def _handle_list(self, state: DialogState) -> DialogResponse:
        try:
            clients = await self._mis.find_clients(last_name=state.last_name, first_name=state.first_name, birth_date=state.birth_date)
        except Exception:
            clients = []

        if not clients:
            return DialogResponse(reply="Я не нашёл вас в базе. Проверьте, пожалуйста, данные.", step=STEP_ASK_NAME)

        client = clients[0]
        state.client_id = client.id
        visits = await self._mis.list_visits(client_id=client.id, status=VisitStatus.PLANNED)

        if not visits:
            state.step = STEP_BOOKED
            return DialogResponse(reply="У вас нет активных записей, которые можно отменить.", step=state.step)

        visit = visits[0]
        state.visit_id = visit.id
        state.step = STEP_CANCEL_CONFIRM

        return DialogResponse(reply=f"У вас есть запись к {visit.doctor.full_name} на {visit.scheduled_at}. Отменить её? Скажите «да» или «нет».", step=state.step)

    async def _handle_confirm(self, state: DialogState, raw_text: str) -> DialogResponse:
        lowered = raw_text.lower()
        yes = any(w in lowered for w in ["да", "подтверждаю", "верно", "ага", "хорошо", "ок"])
        no = any(w in lowered for w in ["нет", "не надо"])

        if no or not yes:
            state.step = STEP_BOOKED
            return DialogResponse(reply="Хорошо, оставляю запись в силе. Что-нибудь ещё?", step=state.step)

        try:
            await self._mis.update_visit(visit_id=state.visit_id, data=VisitUpdate(status=VisitStatus.CANCELLED))
            state.step = STEP_BOOKED
            return DialogResponse(reply="Готово, запись отменена. Спасибо, что предупредили. Что-нибудь ещё?", step=state.step)
        except Exception as exc:
            state.step = STEP_BOOKED
            return DialogResponse(reply=f"Не удалось отменить запись: {exc}.", step=state.step)