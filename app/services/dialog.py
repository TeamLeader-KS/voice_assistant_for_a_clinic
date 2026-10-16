"""Диалоговый движок C-01 «Запись к терапевту» + C-14 «Экстренная ситуация».

State machine:
    greeting → ask_name → ask_specialty → offer_slots → confirm → booked
    (в любой момент → escalated при красном флаге)

Состояние диалога хранится в памяти (для MVP).
На проде — Redis по ключу dialog:{call_id}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.constants import RED_FLAG_CATEGORY_A
from app.schemas.mis import ClientCreate, EscalationCreate, VisitCreate
from app.services.mis_client import MISClientProtocol
from app.services.nlu import ParsedUtterance, parse
from app.services.red_flags import RedFlag, detect as detect_red_flag
from app.services.schedule import ScheduleService, Slot
from app.services.transfer import build_emergency_card, build_urgent_card


# Состояние диалога
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
    step: str = STEP_GREETING
    last_name: str | None = None
    first_name: str | None = None
    birth_date: str | None = None
    specialty: str | None = None
    offered_slots: list[Slot] = field(default_factory=list)
    selected_slot: Slot | None = None
    client_id: int | None = None
    visit_id: int | None = None
    # Поля для C-14 и общей работы
    started_at: str = field(
        default_factory=lambda: datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    )
    full_name: str | None = None
    red_flag: RedFlag | None = None


@dataclass
class DialogResponse:
    """Ответ ассистента."""

    reply: str
    step: str
    visit_id: int | None = None
    booked: bool = False
    escalated: bool = False
    red_flag_category: str | None = None


class DialogEngine:
    """Диалоговый движок C-01 + C-14."""

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

        # КРАСНЫЙ ФЛАГ: проверяем ПЕРВЫМ делом, до всего остального
        red_flag = detect_red_flag(text)
        if red_flag is not None:
            return await self._handle_red_flag(state, red_flag, text)

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

        # Fallback — сбрасываем и начинаем заново
        state.step = STEP_GREETING
        return DialogResponse(
            reply="Извините, я не понял. Давайте начнём сначала. Чем могу помочь?",
            step=state.step,
        )

    async def _handle_red_flag(
        self,
        state: DialogState,
        red_flag: RedFlag,
        raw_text: str,
    ) -> DialogResponse:
        """Обработать красный флаг: прервать сценарий, создать эскалацию."""
        # Дособерём ФИО, если оно есть по частям
        if not state.full_name and state.last_name and state.first_name:
            state.full_name = f"{state.last_name} {state.first_name}"

        # Собираем карточку перевода
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

        # Создаём эскалацию в MIS, если пациент уже идентифицирован
        if state.client_id is not None:
            try:
                await self._mis.create_escalation(
                    EscalationCreate(
                        client_id=state.client_id,
                        description=card.to_escalation_description(),
                    )
                )
            except Exception:  # noqa: BLE001
                # Если MIS не отвечает — не блокируем экстренную помощь
                pass

        # Переводим диалог в терминальное состояние
        state.step = STEP_ESCALATED
        state.red_flag = red_flag

        return DialogResponse(
            reply=red_flag.phrase,
            step=state.step,
            escalated=True,
            red_flag_category=red_flag.category,
        )

   
    # Шаги C-01
    async def _handle_greeting(
        self, state: DialogState, parsed: ParsedUtterance
    ) -> DialogResponse:
        state.step = STEP_ASK_NAME
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
        state.full_name = f"{parsed.last_name} {parsed.first_name}"
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
            lines.append(f"{i}. {slot.date} в {slot.start}, {slot.doctor_name}")
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
        yes = any(
            w in lowered
            for w in ["да", "подтверждаю", "верно", "ага", "хорошо", "ок"]
        )
        no = any(w in lowered for w in ["нет", "не надо", "другое", "измени"])

        if no or not yes:
            state.step = STEP_OFFER_SLOTS
            return DialogResponse(
                reply="Хорошо, выберите другой вариант. Назовите номер.",
                step=state.step,
            )

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

        client, _created = await self._mis.register_client(
            ClientCreate(
                last_name=state.last_name,
                first_name=state.first_name,
                birth_date=state.birth_date,
            )
        )
        state.client_id = client.id

        doctor_id = await self._schedule.resolve_doctor_id(
            slot.doctor_excel_id, self._mis
        )

        visit = await self._mis.create_visit(
            VisitCreate(
                client_id=client.id,
                doctor_id=doctor_id,
                scheduled_at=slot.scheduled_at,
            )
        )
        state.visit_id = visit.id

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
        word_to_num = {"первый": 1, "второй": 2, "третий": 3}
        lowered = text.lower()
        for word, n in word_to_num.items():
            if word in lowered and n <= max_idx:
                return n - 1
        return None