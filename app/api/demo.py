"""HTTP API для демонстрации диалогового движка.

    POST /demo/dialog    — принять реплику пациента, вернуть ответ ассистента.
    POST /demo/reset     — сбросить состояние диалога по call_id.
    GET  /demo/state/{call_id} — посмотреть состояние (для отладки).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.dialog import DialogEngine
from app.services.mis_factory import create_mis_client
from app.services.schedule import get_schedule

router = APIRouter(prefix="/demo", tags=["demo"])

# Глобальные объекты (для MVP — в памяти)
_mis = create_mis_client()
_schedule = get_schedule()
_engine = DialogEngine(mis=_mis, schedule=_schedule, today=settings.SCHEDULE_TODAY)


# Схемы
class DialogRequest(BaseModel):
    call_id: str = Field(..., min_length=1, description="ID звонка")
    text: str = Field(..., min_length=1, description="Реплика пациента")


class DialogResponseSchema(BaseModel):
    reply: str
    step: str
    visit_id: int | None = None
    booked: bool = False
    escalated: bool = False
    red_flag_category: str | None = None


class ResetResponse(BaseModel):
    ok: bool = True


class StateResponse(BaseModel):
    call_id: str
    step: str
    last_name: str | None
    first_name: str | None
    birth_date: str | None
    specialty: str | None
    visit_id: int | None


# Эндпоинты
@router.post("/dialog", response_model=DialogResponseSchema)
async def dialog(request: DialogRequest) -> DialogResponseSchema:
    """Обработать одну реплику пациента."""
    try:
        response = await _engine.handle(request.call_id, request.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DialogResponseSchema(
        reply=response.reply,
        step=response.step,
        visit_id=response.visit_id,
        booked=response.booked,
        escalated=response.escalated,
        red_flag_category=response.red_flag_category,
    )


@router.post("/reset", response_model=ResetResponse)
async def reset(call_id: str) -> ResetResponse:
    """Сбросить состояние диалога."""
    _engine._states.pop(call_id, None)  # noqa: SLF001
    return ResetResponse()


@router.get("/state/{call_id}", response_model=StateResponse)
async def state(call_id: str) -> StateResponse:
    """Посмотреть состояние диалога (отладка)."""
    st = _engine._states.get(call_id)  # noqa: SLF001
    if st is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return StateResponse(
        call_id=st.call_id,
        step=st.step,
        last_name=st.last_name,
        first_name=st.first_name,
        birth_date=st.birth_date,
        specialty=st.specialty,
        visit_id=st.visit_id,
    )