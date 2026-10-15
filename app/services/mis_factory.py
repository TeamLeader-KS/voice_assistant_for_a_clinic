"""Фабрика MIS-клиента: выбор реализации по настройке MIS_MODE.

Режимы:
    - "mock" — in-memory мок, работает без токена (разработка и тесты).
    - "real" — httpx-клиент к реальному стенду «Регистратура».

Использование:
    from app.services.mis_factory import create_mis_client

    client = create_mis_client()
    doctors = await client.list_doctors(specialty="терапевт")

    # Если это MISClient (реальный) — не забыть закрыть:
    if hasattr(client, "aclose"):
        await client.aclose()
"""

from __future__ import annotations

from app.config import settings
from app.services.mis_client import MISClient, MISClientProtocol
from app.services.mis_client_mock import MISClientMock


def create_mis_client(mode: str | None = None) -> MISClientProtocol:
    """Создать MIS-клиент по режиму.

    Аргументы:
        mode: "mock" или "real". Если None — берётся settings.MIS_MODE.

    Возвращает:
        MISClientMock или MISClient.

    Исключения:
        ValueError: неизвестный режим.
    """
    resolved = (mode or settings.MIS_MODE).strip().lower()

    if resolved == "mock":
        return MISClientMock()

    if resolved == "real":
        if not settings.MIS_TOKEN:
            raise ValueError(
                "MIS_MODE=real, но MIS_TOKEN пуст. "
                "Укажи токен команды в .env или переключись на MIS_MODE=mock."
            )
        return MISClient(
            base_url=settings.MIS_BASE_URL,
            token=settings.MIS_TOKEN,
        )

    raise ValueError(
        f"Неизвестный MIS_MODE: {resolved!r}. Ожидается 'mock' или 'real'."
    )