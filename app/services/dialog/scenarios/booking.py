"""Сценарий C-01 «Запись на приём»."""

from __future__ import annotations

from app.schemas.mis import ClientCreate, VisitCreate
from app.services.dialog.base import ScenarioProtocol
from app.services.dialog.state import (
    DialogResponse, DialogState, STEP_ASK_NAME, STEP_ASK_SPECIALTY,
    STEP_BOOKED, STEP_CONFIRM, STEP_GREETING, STEP_OFFER_SLOTS,
)
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance
from app.services.schedule import ScheduleService


class BookingScenario(ScenarioProtocol):
    name = "booking"

    def __init__(self, mis: MISClientProtocol, schedule: ScheduleService) -> None:
        self._mis = mis
        self._schedule = schedule

    async def handle(self, state: DialogState, parsed: ParsedUtterance | None = None, red_flag=None, raw_text: str = "") -> DialogResponse:
        if state.step == STEP_GREETING:
            return self._handle_greeting(state)
        if state.step == STEP_ASK_NAME:
            return await self._handle_name(state, parsed)
        if state.step == STEP_ASK_SPECIALTY:
            return await self._handle_specialty(state, parsed)
        if state.step == STEP_OFFER_SLOTS:
            return self._handle_slot_choice(state, raw_text)
        if state.step == STEP_CONFIRM:
            return await self._handle_confirm(state, raw_text)
        if state.step == STEP_BOOKED:
            return DialogResponse(reply="Ваша запись уже оформлена. Хотите что-то ещё?", step=state.step, visit_id=state.visit_id)

        state.step = STEP_GREETING
        return DialogResponse(reply="Извините, я не понял. Давайте начнём сначала. Чем могу помочь?", step=state.step)

    def _handle_greeting(self, state: DialogState) -> DialogResponse:
        state.step = STEP_ASK_NAME
        return DialogResponse(
            reply="Здравствуйте! Это голосовой ассистент поликлиники. Я помогу записать вас на приём. Назовите, пожалуйста, вашу фамилию, имя, отчество и дату рождения.",
            step=state.step,
        )

    async def _handle_name(self, state: DialogState, parsed: ParsedUtterance | None) -> DialogResponse:
        if not parsed:
            return DialogResponse(reply="Повторите, пожалуйста.", step=state.step)

        if not (parsed.last_name and parsed.first_name and parsed.birth_date):
            if parsed.last_name and not state.last_name: state.last_name = parsed.last_name
            if parsed.first_name and not state.first_name: state.first_name = parsed.first_name
            if parsed.middle_name and not state.middle_name: state.middle_name = parsed.middle_name
            if parsed.birth_date and not state.birth_date: state.birth_date = parsed.birth_date

            return DialogResponse(
                reply="Пожалуйста, назовите фамилию, имя, отчество и дату рождения. Например: Иванов Пётр Сергеевич, семнадцатое марта тысяча девятьсот восемьдесят пятого года.",
                step=state.step,
            )

        state.last_name = parsed.last_name
        state.first_name = parsed.first_name
        state.middle_name = parsed.middle_name
        state.birth_date = parsed.birth_date
        state.full_name = f"{parsed.last_name} {parsed.first_name}"
        state.step = STEP_ASK_SPECIALTY

        return DialogResponse(
            reply=f"{parsed.first_name} {parsed.last_name}, к какому врачу вас записать? Например, терапевт, педиатр, кардиолог.",
            step=state.step,
        )

    async def _handle_specialty(self, state: DialogState, parsed: ParsedUtterance | None) -> DialogResponse:
        if not parsed or not parsed.specialty:
            return DialogResponse(reply="Уточните, пожалуйста, к какому специалисту вас записать. Например: терапевт, педиатр, кардиолог.", step=state.step)

        state.specialty = parsed.specialty
        slots = await self._schedule.get_free_slots(specialty=parsed.specialty, limit=3)

        if not slots:
            return DialogResponse(reply=f"К сожалению, свободных слотов к {parsed.specialty} в ближайшие 30 дней нет. Попробуйте позже или выберите другого специалиста.", step=STEP_ASK_SPECIALTY)

        state.offered_slots = slots
        state.step = STEP_OFFER_SLOTS
        lines = [f"{i}. {slot.date} в {slot.start}, {slot.doctor_name}" for i, slot in enumerate(slots, 1)]
        options = "\n".join(lines)

        return DialogResponse(reply=f"Есть следующие варианты:\n{options}\nКакой вариант вам подходит? Назовите номер.", step=state.step)

    def _handle_slot_choice(self, state: DialogState, raw_text: str) -> DialogResponse:
        idx = self._extract_choice(raw_text, len(state.offered_slots))
        if idx is None:
            return DialogResponse(reply="Пожалуйста, назовите номер варианта: 1, 2 или 3.", step=state.step)

        slot = state.offered_slots[idx]
        state.selected_slot = slot
        state.step = STEP_CONFIRM

        return DialogResponse(reply=f"Записываю вас к {slot.doctor_name} на {slot.date} в {slot.start}. Подтверждаете? Скажите «да» или «нет».", step=state.step)

    async def _handle_confirm(self, state: DialogState, raw_text: str) -> DialogResponse:
        lowered = raw_text.lower()
        yes = any(w in lowered for w in ["да", "подтверждаю", "верно", "ага", "хорошо", "ок"])
        no = any(w in lowered for w in ["нет", "не надо", "другое", "измени"])

        if no or not yes:
            state.step = STEP_OFFER_SLOTS
            return DialogResponse(reply="Хорошо, выберите другой вариант. Назовите номер.", step=state.step)

        try:
            return await self._book(state)
        except Exception as exc:
            state.step = STEP_OFFER_SLOTS
            return DialogResponse(reply=f"Не удалось создать запись: {exc}. Попробуйте выбрать другой слот.", step=state.step)

    async def _book(self, state: DialogState) -> DialogResponse:
        slot = state.selected_slot
        assert slot is not None
        assert state.last_name and state.first_name and state.birth_date

        client, _created = await self._mis.register_client(
            ClientCreate(
                last_name=state.last_name,
                first_name=state.first_name,
                middle_name=state.middle_name,
                birth_date=state.birth_date,
            )
        )
        state.client_id = client.id
        doctor_id = await self._schedule.resolve_doctor_id(slot.doctor_excel_id, self._mis)
        visit = await self._mis.create_visit(VisitCreate(client_id=client.id, doctor_id=doctor_id, scheduled_at=slot.scheduled_at))
        state.visit_id = visit.id
        await self._schedule.book_slot(slot.doctor_excel_id, slot.scheduled_at)
        state.step = STEP_BOOKED

        return DialogResponse(
            reply=f"Готово! Вы записаны к {slot.doctor_name} на {slot.date} в {slot.start}. Номер вашей записи: {visit.id}. Ждём вас в поликлинике.",
            step=state.step, visit_id=visit.id, booked=True,
        )

    @staticmethod
    def _extract_choice(text: str, max_idx: int) -> int | None:
        for token in text.split():
            token = token.strip(".,!?;:")
            if token.isdigit():
                n = int(token)
                if 1 <= n <= max_idx: return n - 1
        word_to_num = {"первый": 1, "второй": 2, "третий": 3}
        lowered = text.lower()
        for word, n in word_to_num.items():
            if word in lowered and n <= max_idx: return n - 1
        return None