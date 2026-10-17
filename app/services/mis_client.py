"""Клиент REST API тестового стенда «Регистратура».

Содержит:
    - MISClientProtocol — интерфейс, общий для мока и реального клиента.
    - MISClient — httpx-реализация для работы с реальным стендом.

Особенности стенда, которые учитывает клиент:
    - Лимит 10 запросов в минуту → при 429 читаем «Retry-After» и бросаем MISRateLimited.
    - Даты — строки «ДД.ММ.ГГГГ» и «ДД.ММ.ГГГГ ЧЧ:ММ» (GMT+4).
    - Повторная регистрация клиента → 200, а не 201 → возвращаем (client, created=False).
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app.core.exceptions import (
    MISConflict,
    MISError,
    MISNotFound,
    MISRateLimited,
    MISServerError,
    MISUnauthorized,
    MISValidationError,
)
from app.schemas.mis import (
    Client,
    ClientCreate,
    ClientUpdate,
    Doctor,
    Escalation,
    EscalationCreate,
    MISErrorBody,
    Visit,
    VisitCreate,
    VisitStatus,
    VisitUpdate,
)


class MISClientProtocol(Protocol):
    """Интерфейс MIS-клиента, общий для мока и реальной реализации."""

    async def list_doctors(
        self,
        specialty: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Doctor]: ...

    async def register_client(self, data: ClientCreate) -> tuple[Client, bool]: ...

    async def find_clients(
        self,
        last_name: str | None = None,
        first_name: str | None = None,
        birth_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Client]: ...

    async def get_client(self, client_id: int) -> Client: ...

    async def update_client(self, client_id: int, data: ClientUpdate) -> Client: ...

    async def create_visit(self, data: VisitCreate) -> Visit: ...

    async def list_visits(
        self,
        client_id: int | None = None,
        doctor_id: int | None = None,
        status: VisitStatus | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Visit]: ...

    async def get_visit(self, visit_id: int) -> Visit: ...

    async def update_visit(self, visit_id: int, data: VisitUpdate) -> Visit: ...

    async def create_escalation(self, data: EscalationCreate) -> Escalation: ...

    async def list_escalations(
        self,
        client_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Escalation]: ...

    async def get_escalation(self, escalation_id: int) -> Escalation: ...


class MISClient:
    """HTTP-клиент стенда «Регистратура».

    Пример:
        client = MISClient(base_url="...", token="...")
        doctors = await client.list_doctors(specialty="терапевт")
        await client.aclose()
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        """Закрыть HTTP-сессию."""
        await self._client.aclose()

    async def __aenter__(self) -> "MISClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ─────────────────────────────────────────────────────
    # Внутренние помощники
    # ─────────────────────────────────────────────────────

    def _raise_from_response(self, response: httpx.Response) -> None:
        """Преобразовать ответ стенда с ошибкой в кастомное исключение."""
        retry_after: int | None = None
        if response.status_code == 429:
            raw = response.headers.get("Retry-After")
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = None

        code: str | None = None
        message = ""
        try:
            body = MISErrorBody.model_validate(response.json())
            code = body.code.value
            message = body.message
        except Exception:
            message = response.text or f"HTTP {response.status_code}"

        exc_map: dict[int, type[MISError]] = {
            400: MISValidationError,
            401: MISUnauthorized,
            404: MISNotFound,
            409: MISConflict,
            500: MISServerError,
        }

        if response.status_code == 429:
            raise MISRateLimited(
                message, retry_after=retry_after, code=code, status_code=429
            )

        exc_cls = exc_map.get(response.status_code, MISServerError)
        raise exc_cls(message, code=code, status_code=response.status_code)

    # ─────────────────────────────────────────────────────
    # Врачи
    # ─────────────────────────────────────────────────────

    async def list_doctors(
        self,
        specialty: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Doctor]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if specialty:
            params["specialty"] = specialty

        response = await self._client.get("/doctors", params=params)
        if response.status_code != 200:
            self._raise_from_response(response)
        return [Doctor.model_validate(item) for item in response.json()]

    # ─────────────────────────────────────────────────────
    # Клиенты
    # ─────────────────────────────────────────────────────

    async def register_client(self, data: ClientCreate) -> tuple[Client, bool]:
        response = await self._client.post(
            "/clients", json=data.model_dump(exclude_none=True)
        )
        if response.status_code not in (200, 201):
            self._raise_from_response(response)
        created = response.status_code == 201
        return Client.model_validate(response.json()), created

    async def find_clients(
        self,
        last_name: str | None = None,
        first_name: str | None = None,
        birth_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Client]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if last_name:
            params["last_name"] = last_name
        if first_name:
            params["first_name"] = first_name
        if birth_date:
            params["birth_date"] = birth_date

        response = await self._client.get("/clients", params=params)
        if response.status_code != 200:
            self._raise_from_response(response)
        return [Client.model_validate(item) for item in response.json()]

    async def get_client(self, client_id: int) -> Client:
        response = await self._client.get(f"/clients/{client_id}")
        if response.status_code != 200:
            self._raise_from_response(response)
        return Client.model_validate(response.json())

    async def update_client(self, client_id: int, data: ClientUpdate) -> Client:
        response = await self._client.patch(
            f"/clients/{client_id}", json=data.model_dump(exclude_unset=True)
        )
        if response.status_code != 200:
            self._raise_from_response(response)
        return Client.model_validate(response.json())

    # ─────────────────────────────────────────────────────
    # Записи на приём
    # ─────────────────────────────────────────────────────

    async def create_visit(self, data: VisitCreate) -> Visit:
        response = await self._client.post("/visits", json=data.model_dump())
        if response.status_code != 201:
            self._raise_from_response(response)
        return Visit.model_validate(response.json())

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
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if client_id is not None:
            params["client_id"] = client_id
        if doctor_id is not None:
            params["doctor_id"] = doctor_id
        if status is not None:
            params["status"] = status.value
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        response = await self._client.get("/visits", params=params)
        if response.status_code != 200:
            self._raise_from_response(response)
        return [Visit.model_validate(item) for item in response.json()]

    async def get_visit(self, visit_id: int) -> Visit:
        response = await self._client.get(f"/visits/{visit_id}")
        if response.status_code != 200:
            self._raise_from_response(response)
        return Visit.model_validate(response.json())

    async def update_visit(self, visit_id: int, data: VisitUpdate) -> Visit:
        response = await self._client.patch(
            f"/visits/{visit_id}", json=data.model_dump(exclude_unset=True)
        )
        if response.status_code != 200:
            self._raise_from_response(response)
        return Visit.model_validate(response.json())

    # ─────────────────────────────────────────────────────
    # Заявки на соединение со специалистом
    # ─────────────────────────────────────────────────────

    async def create_escalation(self, data: EscalationCreate) -> Escalation:
        response = await self._client.post("/escalations", json=data.model_dump())
        if response.status_code != 201:
            self._raise_from_response(response)
        return Escalation.model_validate(response.json())

    async def list_escalations(
        self,
        client_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Escalation]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if client_id is not None:
            params["client_id"] = client_id

        response = await self._client.get("/escalations", params=params)
        if response.status_code != 200:
            self._raise_from_response(response)
        return [Escalation.model_validate(item) for item in response.json()]

    async def get_escalation(self, escalation_id: int) -> Escalation:
        response = await self._client.get(f"/escalations/{escalation_id}")
        if response.status_code != 200:
            self._raise_from_response(response)
        return Escalation.model_validate(response.json())