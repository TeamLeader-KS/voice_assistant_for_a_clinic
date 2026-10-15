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


def _seed_doctors_from_schedule(mock: MISClientMock) -> None:
    """Засеять мок врачами из schedule.xlsx.

    Берём уникальных врачей из листа «Слоты» и создаём для них
    записи в справочнике MIS с числовыми ID (D001 → 1, D002 → 2, ...).
    """
    from pathlib import Path

    from app.config import settings
    from app.schemas.mis import Doctor
    from app.services.schedule import ScheduleService

    path = Path(settings.SCHEDULE_XLSX_PATH)
    if not path.exists():
        return  # нет файла — мок остаётся пустым, тесты всё равно работают

    schedule = ScheduleService(str(path))
    schedule.load()

    # Собираем уникальных врачей: {excel_id: (full_name, specialty)}
    doctors: dict[str, tuple[str, str]] = {}
    for slot in schedule._slots:  # noqa: SLF001
        if slot.doctor_excel_id not in doctors:
            doctors[slot.doctor_excel_id] = (slot.doctor_name, slot.specialty)

    # Создаём Doctor с числовым ID: "D001" → 1
    mis_doctors: list[Doctor] = []
    for excel_id, (full_name, specialty) in doctors.items():
        try:
            numeric_id = int(excel_id.lstrip("Dd"))
        except ValueError:
            continue
        mis_doctors.append(
            Doctor(
                id=numeric_id,
                full_name=full_name,
                specialty=specialty,
                is_active=True,
            )
        )

    mock.seed_doctors(mis_doctors)

    
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
        mock = MISClientMock()
        _seed_doctors_from_schedule(mock)
    return mock

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