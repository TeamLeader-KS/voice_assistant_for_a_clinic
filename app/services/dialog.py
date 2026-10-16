"""Диалоговый движок C-01 «Запись к терапевту».

State machine:
    greeting → ask_name → ask_specialty → offer_slots → confirm → booked

Состояние диалога хранится в памяти (для MVP).
На проде — Redis по ключу dialog:{call_id}.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance, parse
from app.services.schedule import ScheduleService, Slot
from app.schemas.mis import ClientCreate, VisitCreate


# Состояние диалога
STEP_GREETING = "greeting"
STEP_ASK_NAME = "ask_name"
STEP_ASK_SPECIALTY = "ask_specialty"
STEP_OFFER_SLOTS = "offer_slots"
STEP_CONFIRM = "confirm"
STEP_BOOKED = "booked"
STEP_FALLBACK = "fallback"


@dataclass
class DialogState:
    """Состояние диалога по одному звонку."""

    call_id: str
    step: str = STEP_GREETING
    last_name: str | None = None
    first_name: str | None = None
    birth_date: str | None = None
    specialty: str | None = None
    offered_slots: list[Slot] = field(default_factory=list)
    selected_slot: Slot | None = None
    client_id: int | None = None
    visit_id: int | None = None


@dataclass
class DialogResponse:
    """Ответ ассистента."""

    reply: str
    step: str
    visit_id: int | None = None
    booked: bool = False


# Движок
class DialogEngine:
    """Диалоговый движок C-01."""

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

    def _get_state(self, call_id: str) -> DialogState:
        if call_id not in self._states:
            self._states[call_id] = DialogState(call_id=call_id)
        return self._states[call_id]

    async def handle(self, call_id: str, text: str) -> DialogResponse:
        """Обработать реплику пациента."""
        state = self._get_state(call_id)
        parsed = parse(text, self._today)

        # Первое обращение — всегда приветствие
        if state.step == STEP_GREETING:
            return await self._handle_greeting(state, parsed)

        if state.step == STEP_ASK_NAME:
            return await self._handle_name(state, parsed)

        if state.step == STEP_ASK_SPECIALTY:
            return await self._handle_specialty(state, parsed)

        if state.step == STEP_OFFER_SLOTS:
            return await self._handle_slot_choice(state, parsed, text)

        if state.step == STEP_CONFIRM:
            return await self._handle_confirm(state, parsed, text)

        if state.step == STEP_BOOKED:
            return DialogResponse(
                reply="Ваша запись уже оформлена. Хотите что-то ещё?",
                step=state.step,
                visit_id=state.visit_id,
            )

        # Fallback — сбрасываем и начинаем заново
        state.step = STEP_GREETING
        return DialogResponse(
            reply="Извините, я не понял. Давайте начнём сначала. Чем могу помочь?",
            step=state.step,
        )

    
    # Шаги
    async def _handle_greeting(
        self, state: DialogState, parsed: ParsedUtterance
    ) -> DialogResponse:
        state.step = STEP_ASK_NAME

        # Если интент — не «book», всё равно ведём в C-01 (для MVP)
        return DialogResponse(
            reply=(
                "Здравствуйте! Это голосовой ассистент поликлиники. "
                "Я помогу записать вас на приём. "
                "Назовите, пожалуйста, вашу фамилию, имя и дату рождения."
            ),
            step=state.step,
        )

    async def _handle_name(
        self, state: DialogState, parsed: ParsedUtterance
    ) -> DialogResponse:
        if not (parsed.last_name and parsed.first_name and parsed.birth_date):
            # Пробуем частично заполнить, если что-то распознали
            if parsed.last_name and not state.last_name:
                state.last_name = parsed.last_name
            if parsed.first_name and not state.first_name:
                state.first_name = parsed.first_name
            if parsed.birth_date and not state.birth_date:
                state.birth_date = parsed.birth_date

            return DialogResponse(
                reply=(
                    "Пожалуйста, назовите фамилию, имя и дату рождения "
                    "в формате: Иванов Пётр, семнадцатое марта тысяча девятьсот восемьдесят пятого года."
                ),
                step=state.step,
            )

        state.last_name = parsed.last_name
        state.first_name = parsed.first_name
        state.birth_date = parsed.birth_date
        state.step = STEP_ASK_SPECIALTY

        return DialogResponse(
            reply=(
                f"{parsed.first_name} {parsed.last_name}, к какому врачу вас записать? "
                f"Например, терапевт, педиатр, кардиолог."
            ),
            step=state.step,
        )

    async def _handle_specialty(
        self, state: DialogState, parsed: ParsedUtterance
    ) -> DialogResponse:
        if not parsed.specialty:
            return DialogResponse(
                reply=(
                    "Уточните, пожалуйста, к какому специалисту вас записать. "
                    "Например: терапевт, педиатр, кардиолог."
                ),
                step=state.step,
            )

        state.specialty = parsed.specialty

        # Ищем свободные слоты
        slots = await self._schedule.get_free_slots(
            specialty=parsed.specialty, limit=3
        )

        if not slots:
            return DialogResponse(
                reply=(
                    f"К сожалению, свободных слотов к {parsed.specialty} "
                    f"в ближайшие 30 дней нет. Попробуйте позже или выберите другого специалиста."
                ),
                step=STEP_ASK_SPECIALTY,
            )

        state.offered_slots = slots
        state.step = STEP_OFFER_SLOTS

        lines = []
        for i, slot in enumerate(slots, 1):
            lines.append(
                f"{i}. {slot.date} в {slot.start}, {slot.doctor_name}"
            )
        options = "\n".join(lines)

        return DialogResponse(
            reply=(
                f"Есть следующие варианты:\n{options}\n"
                f"Какой вариант вам подходит? Назовите номер."
            ),
            step=state.step,
        )

    async def _handle_slot_choice(
        self,
        state: DialogState,
        parsed: ParsedUtterance,
        raw_text: str,
    ) -> DialogResponse:
        # Ищем цифру в тексте
        idx = self._extract_choice(raw_text, len(state.offered_slots))
        if idx is None:
            return DialogResponse(
                reply="Пожалуйста, назовите номер варианта: 1, 2 или 3.",
                step=state.step,
            )

        slot = state.offered_slots[idx]
        state.selected_slot = slot
        state.step = STEP_CONFIRM

        return DialogResponse(
            reply=(
                f"Записываю вас к {slot.doctor_name} "
                f"на {slot.date} в {slot.start}. Подтверждаете? "
                f"Скажите «да» или «нет»."
            ),
            step=state.step,
        )

    async def _handle_confirm(
        self,
        state: DialogState,
        parsed: ParsedUtterance,
        raw_text: str,
    ) -> DialogResponse:
        lowered = raw_text.lower()
        yes = any(w in lowered for w in ["да", "подтверждаю", "верно", "ага", "хорошо", "ок"])
        no = any(w in lowered for w in ["нет", "не надо", "другое", "измени"])

        if no or not yes:
            state.step = STEP_OFFER_SLOTS
            return DialogResponse(
                reply="Хорошо, выберите другой вариант. Назовите номер.",
                step=state.step,
            )

        # Создаём запись
        try:
            return await self._book(state)
        except Exception as exc:  # noqa: BLE001
            state.step = STEP_OFFER_SLOTS
            return DialogResponse(
                reply=(
                    f"Не удалось создать запись: {exc}. "
                    f"Попробуйте выбрать другой слот."
                ),
                step=state.step,
            )


    # Создание записи
    async def _book(self, state: DialogState) -> DialogResponse:
        slot = state.selected_slot
        assert slot is not None
        assert state.last_name and state.first_name and state.birth_date

        # 1. Регистрируем/находим клиента
        client, _created = await self._mis.register_client(
            ClientCreate(
                last_name=state.last_name,
                first_name=state.first_name,
                birth_date=state.birth_date,
            )
        )
        state.client_id = client.id

        # 2. Сопоставляем врача из Excel с MIS
        doctor_id = await self._schedule.resolve_doctor_id(
            slot.doctor_excel_id, self._mis
        )

        # 3. Создаём запись
        visit = await self._mis.create_visit(
            VisitCreate(
                client_id=client.id,
                doctor_id=doctor_id,
                scheduled_at=slot.scheduled_at,
            )
        )
        state.visit_id = visit.id

        # 4. Помечаем слот занятым
        await self._schedule.book_slot(slot.doctor_excel_id, slot.scheduled_at)

        state.step = STEP_BOOKED

        return DialogResponse(
            reply=(
                f"Готово! Вы записаны к {slot.doctor_name} "
                f"на {slot.date} в {slot.start}. "
                f"Номер вашей записи: {visit.id}. "
                f"Ждём вас в поликлинике."
            ),
            step=state.step,
            visit_id=visit.id,
            booked=True,
        )

    
    # Помощники
    @staticmethod
    def _extract_choice(text: str, max_idx: int) -> int | None:
        """Найти номер варианта в тексте (1-based → 0-based)."""
        for token in text.split():
            token = token.strip(".,!?;:")
            if token.isdigit():
                n = int(token)
                if 1 <= n <= max_idx:
                    return n - 1
        # Словами
        word_to_num = {"первый": 1, "второй": 2, "третий": 3}
        lowered = text.lower()
        for word, n in word_to_num.items():
            if word in lowered and n <= max_idx:
                return n - 1
        return None