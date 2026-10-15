"""In-memory мок MIS-клиента для локальной разработки и тестов.

Реализует тот же интерфейс, что и MISClient, но хранит данные в памяти
процесса. Позволяет разрабатывать и тестировать сценарии C-01…C-15
без токена и без обращения к реальному стенду.

Поведение приближено к реальному стенду:
    - Повторная регистрация клиента возвращает существующую карточку и created=False.
    - Обращение к несуществующему объекту → MISNotFound.
    - Патч отменённой/завершённой записи → MISConflict.
    - Патч записи к деактивированному врачу → MISConflict (кроме status=CANCELLED).
    - Создание записи к деактивированному врачу → MISValidationError.
"""

from __future__ import annotations

from datetime import datetime
from itertools import count

from app.core.exceptions import (
    MISConflict,
    MISNotFound,
    MISValidationError,
)
from app.schemas.mis import (
    Client,
    ClientCreate,
    ClientUpdate,
    Doctor,
    Escalation,
    EscalationCreate,
    Visit,
    VisitCreate,
    VisitStatus,
    VisitUpdate,
)

_GMT4_STAMP = "%d.%m.%Y %H:%M"


def _now() -> str:
    """Текущее время в формате стенда (без учёта TZ — для мока достаточно)."""
    return datetime.now().strftime(_GMT4_STAMP)


class MISClientMock:
    """In-memory реализация MISClientProtocol.

    Пример:
        mock = MISClientMock()
        mock.seed_doctors([
            Doctor(id=1, full_name="Иванова Мария Петровна",
                   specialty="терапевт", is_active=True),
        ])
        client, created = await mock.register_client(
            ClientCreate(last_name="Иванов", first_name="Пётр",
                         birth_date="17.03.1985")
        )
    """

    def __init__(self) -> None:
        self._doctors: dict[int, Doctor] = {}
        self._clients: dict[int, Client] = {}
        self._visits: dict[int, Visit] = {}
        self._escalations: dict[int, Escalation] = {}

        self._client_ids = count(1)
        self._visit_ids = count(1)
        self._escalation_ids = count(1)

    # ─────────────────────────────────────────────────────
    # Помощники для тестов и сидов
    # ─────────────────────────────────────────────────────

    def seed_doctors(self, doctors: list[Doctor]) -> None:
        """Заполнить справочник врачей."""
        for doctor in doctors:
            self._doctors[doctor.id] = doctor

    def reset(self) -> None:
        """Очистить всё состояние мока."""
        self._doctors.clear()
        self._clients.clear()
        self._visits.clear()
        self._escalations.clear()
        self._client_ids = count(1)
        self._visit_ids = count(1)
        self._escalation_ids = count(1)

    # ─────────────────────────────────────────────────────
    # Врачи
    # ─────────────────────────────────────────────────────

    async def list_doctors(
        self,
        specialty: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Doctor]:
        items = sorted(self._doctors.values(), key=lambda d: d.id)
        if specialty:
            needle = specialty.strip().lower()
            items = [d for d in items if d.specialty.strip().lower() == needle]
        return items[offset : offset + limit]

    # ─────────────────────────────────────────────────────
    # Клиенты
    # ─────────────────────────────────────────────────────

    async def register_client(self, data: ClientCreate) -> tuple[Client, bool]:
        key = (data.last_name.strip(), data.first_name.strip(), data.birth_date.strip())
        for client in self._clients.values():
            existing_key = (
                client.last_name.strip(),
                client.first_name.strip(),
                client.birth_date.strip(),
            )
            if existing_key == key:
                return client, False

        new_id = next(self._client_ids)
        client = Client(
            id=new_id,
            last_name=data.last_name,
            first_name=data.first_name,
            middle_name=data.middle_name,
            birth_date=data.birth_date,
            comment=data.comment,
            created_at=_now(),
        )
        self._clients[new_id] = client
        return client, True

    async def find_clients(
        self,
        last_name: str | None = None,
        first_name: str | None = None,
        birth_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Client]:
        items = sorted(self._clients.values(), key=lambda c: c.id)
        if last_name:
            items = [c for c in items if c.last_name == last_name]
        if first_name:
            items = [c for c in items if c.first_name == first_name]
        if birth_date:
            items = [c for c in items if c.birth_date == birth_date]
        return items[offset : offset + limit]

    async def get_client(self, client_id: int) -> Client:
        client = self._clients.get(client_id)
        if client is None:
            raise MISNotFound(
                f"Клиент {client_id} не найден", code="НЕ_НАЙДЕНО", status_code=404
            )
        return client

    async def update_client(self, client_id: int, data: ClientUpdate) -> Client:
        client = await self.get_client(client_id)
        updated = client.model_copy(
            update=data.model_dump(exclude_unset=True),
        )
        self._clients[client_id] = updated
        return updated

    # ─────────────────────────────────────────────────────
    # Записи на приём
    # ─────────────────────────────────────────────────────

    async def create_visit(self, data: VisitCreate) -> Visit:
        if data.client_id not in self._clients:
            raise MISValidationError(
                "Поле «client_id» указывает на несуществующего клиента",
                code="НЕВЕРНЫЙ_ЗАПРОС",
                status_code=400,
            )
        doctor = self._doctors.get(data.doctor_id)
        if doctor is None:
            raise MISValidationError(
                "Поле «doctor_id» указывает на врача вне справочника",
                code="НЕВЕРНЫЙ_ЗАПРОС",
                status_code=400,
            )
        if not doctor.is_active:
            raise MISValidationError(
                "Поле «doctor_id» указывает на деактивированного врача: "
                "запись к нему невозможна.",
                code="НЕВЕРНЫЙ_ЗАПРОС",
                status_code=400,
            )

        new_id = next(self._visit_ids)
        now = _now()
        visit = Visit(
            id=new_id,
            client_id=data.client_id,
            doctor=doctor,
            scheduled_at=data.scheduled_at,
            status=VisitStatus.PLANNED,
            created_at=now,
            updated_at=now,
        )
        self._visits[new_id] = visit
        return visit

    async def list_visits(
        self,
        client_id: int | None = None,
        doctor_id: int | None = None,
        status: VisitStatus | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Visit]:
        items = sorted(self._visits.values(), key=lambda v: (v.scheduled_at, v.id))
        if client_id is not None:
            items = [v for v in items if v.client_id == client_id]
        if doctor_id is not None:
            items = [v for v in items if v.doctor.id == doctor_id]
        if status is not None:
            items = [v for v in items if v.status == status]
        # date_from / date_to в моке не фильтруем — оставляем на потом
        return items[offset : offset + limit]

    async def get_visit(self, visit_id: int) -> Visit:
        visit = self._visits.get(visit_id)
        if visit is None:
            raise MISNotFound(
                f"Запись {visit_id} не найдена", code="НЕ_НАЙДЕНО", status_code=404
            )
        return visit

    async def update_visit(self, visit_id: int, data: VisitUpdate) -> Visit:
        visit = await self.get_visit(visit_id)
        payload = data.model_dump(exclude_unset=True)

        # Терминальные статусы не подлежат изменению, кроме повторной отмены.
        if visit.status in (VisitStatus.CANCELLED, VisitStatus.COMPLETED):
            only_cancel = payload.get("status") == VisitStatus.CANCELLED
            if not only_cancel or len(payload) > 1:
                raise MISConflict(
                    f"Запись в статусе «{visit.status.value}» изменению не подлежит",
                    code="КОНФЛИКТ_СТАТУСА",
                    status_code=409,
                )

        # Врач деактивирован — разрешена только отмена.
        if not visit.doctor.is_active:
            only_cancel = payload.get("status") == VisitStatus.CANCELLED
            if not only_cancel or len(payload) > 1:
                raise MISConflict(
                    "Врач записи на приём деактивирован: запись можно только отменить.",
                    code="КОНФЛИКТ_СТАТУСА",
                    status_code=409,
                )

        if "doctor_id" in payload and payload["doctor_id"] is not None:
            new_doctor = self._doctors.get(payload["doctor_id"])
            if new_doctor is None:
                raise MISValidationError(
                    "Поле «doctor_id» указывает на врача вне справочника",
                    code="НЕВЕРНЫЙ_ЗАПРОС",
                    status_code=400,
                )
            if not new_doctor.is_active:
                raise MISValidationError(
                    "Поле «doctor_id» указывает на деактивированного врача: "
                    "запись к нему невозможна.",
                    code="НЕВЕРНЫЙ_ЗАПРОС",
                    status_code=400,
                )
            payload["doctor"] = new_doctor

        payload.pop("doctor_id", None)
        updated = visit.model_copy(update=payload)
        updated = updated.model_copy(update={"updated_at": _now()})
        self._visits[visit_id] = updated
        return updated

    # ─────────────────────────────────────────────────────
    # Заявки на соединение со специалистом
    # ─────────────────────────────────────────────────────

    async def create_escalation(self, data: EscalationCreate) -> Escalation:
        if data.client_id not in self._clients:
            raise MISValidationError(
                "Поле «client_id» указывает на несуществующего клиента",
                code="НЕВЕРНЫЙ_ЗАПРОС",
                status_code=400,
            )
        new_id = next(self._escalation_ids)
        escalation = Escalation(
            id=new_id,
            client_id=data.client_id,
            description=data.description,
            created_at=_now(),
        )
        self._escalations[new_id] = escalation
        return escalation

    async def list_escalations(
        self,
        client_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Escalation]:
        items = sorted(
            self._escalations.values(),
            key=lambda e: (e.created_at, e.id),
            reverse=True,
        )
        if client_id is not None:
            items = [e for e in items if e.client_id == client_id]
        return items[offset : offset + limit]

    async def get_escalation(self, escalation_id: int) -> Escalation:
        escalation = self._escalations.get(escalation_id)
        if escalation is None:
            raise MISNotFound(
                f"Заявка {escalation_id} не найдена",
                code="НЕ_НАЙДЕНО",
                status_code=404,
            )
        return escalation