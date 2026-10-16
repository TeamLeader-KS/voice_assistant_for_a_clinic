import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import redis

logger = logging.getLogger(__name__)


class SlotManager:
    """
    Управляет слотами врачей: находит свободные, лочит на время диалога.

    Логика:
    - Свободные слоты = слоты из Excel, которые не заняты в МИС и не залочены.
    - Лок ставится сразу при предложении слота пациенту.
    - Лок автоматически снимается по TTL, если пациент не ответил.
    """

    LOCK_TTL_SECONDS = 180  # 3 минуты на ответ пациента

    def __init__(self, schedule_path: str, redis_client: redis.Redis):
        self.schedule_path = schedule_path
        self.redis = redis_client
        self._schedule = None  # кэш Excel в памяти

    def _load_schedule(self) -> pd.DataFrame:
        """Ленивая загрузка Excel-расписания (один раз)."""
        if self._schedule is None:
            logger.info(f"Загрузка расписания: {self.schedule_path}")
            self._schedule = pd.read_excel(self.schedule_path)
        return self._schedule

    def _lock_key(self, doctor_id: int, slot_datetime: str) -> str:
        """Ключ лока в Redis."""
        return f"slot:{doctor_id}:{slot_datetime}"

    def is_locked(self, doctor_id: int, slot_datetime: str) -> bool:
        """Проверить, залочен ли слот."""
        return bool(self.redis.exists(self._lock_key(doctor_id, slot_datetime)))

    def lock(self, doctor_id: int, slot_datetime: str, call_id: str) -> bool:
        """
        Попытаться залочить слот. Атомарно через SET NX EX.

        Returns:
            True — лок успешно поставлен.
            False — слот уже залочен кем-то другим.
        """
        key = self._lock_key(doctor_id, slot_datetime)
        acquired = self.redis.set(
            key,
            call_id,
            nx=True,  # только если ключа нет
            ex=self.LOCK_TTL_SECONDS,
        )
        if acquired:
            logger.info(f"Слот залочен: {key} (call={call_id})")
            return True
        logger.warning(f"Слот уже залочен: {key}")
        return False

    def unlock(self, doctor_id: int, slot_datetime: str) -> None:
        """Снять лок (например, пациент отказался)."""
        key = self._lock_key(doctor_id, slot_datetime)
        self.redis.delete(key)
        logger.info(f"Слот разлочен: {key}")

    def extend_lock(self, doctor_id: int, slot_datetime: str) -> None:
        """Продлить TTL лока, если диалог идёт дольше 3 минут."""
        key = self._lock_key(doctor_id, slot_datetime)
        self.redis.expire(key, self.LOCK_TTL_SECONDS)

    def get_free_slots(
            self,
            doctor_id: int,
            date: str,
            exclude_locked: bool = True,
    ) -> list[str]:
        """
        Вернуть свободные слоты врача на дату.

        Args:
            doctor_id: ID врача.
            date: Дата в формате ДД.ММ.ГГГГ.
            exclude_locked: Исключать ли залоченные слоты.

        Returns:
            Список свободных слотов в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'.
        """
        df = self._load_schedule()

        # Фильтр по врачу и дате (адаптируйте под реальные колонки Excel)
        mask = (df["doctor_id"] == doctor_id) & (df["date"] == date)
        slots = df.loc[mask, "slot"].tolist()

        if exclude_locked:
            slots = [
                s for s in slots
                if not self.is_locked(doctor_id, s)
            ]

        logger.info(f"Свободных слотов у врача {doctor_id} на {date}: {len(slots)}")
        return slots

    def suggest_and_lock(
            self,
            doctor_id: int,
            date: str,
            call_id: str,
    ) -> Optional[str]:
        """
        Найти первый свободный слот и сразу залочить его.

        Это ключевой метод: ГА видит слот → лочит → предлагает пациенту.
        """
        free_slots = self.get_free_slots(doctor_id, date)
        for slot in free_slots:
            if self.lock(doctor_id, slot, call_id):
                return slot
        return None