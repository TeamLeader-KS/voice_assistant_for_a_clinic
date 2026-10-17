"""Приветствия по времени суток в GMT+4."""
from datetime import datetime, timezone, timedelta

GMT4 = timezone(timedelta(hours=4))


def get_time_of_day(now: datetime | None = None) -> str:
    """Вернуть 'morning' | 'day' | 'evening' | 'night' по локальному времени GMT+4."""
    if now is None:
        now = datetime.now(GMT4)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=GMT4)
    else:
        now = now.astimezone(GMT4)

    hour = now.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 23:
        return "evening"
    return "night"


GREETINGS = {
    "morning": "Доброе утро",
    "day": "Добрый день",
    "evening": "Добрый вечер",
    "night": "Доброй ночи",
}


def get_greeting(now: datetime | None = None) -> str:
    """Вернуть 'Доброе утро' / 'Добрый день' / ... по времени GMT+4."""
    return GREETINGS[get_time_of_day(now)]


# ▼▼▼ ДОБАВИТЬ ЭТУ ФУНКЦИЮ В КОНЕЦ ФАЙЛА ▼▼▼
def get_greeting_reply() -> str:
    """Готовое приветствие с 'Алло' для ответа на входящий звонок."""
    tod = get_time_of_day()
    if tod == "morning":
        return "Алло, доброе утро! Это голосовой ассистент поликлиники. Чем могу помочь?"
    if tod == "day":
        return "Алло, добрый день! Это голосовой ассистент поликлиники. Чем могу помочь?"
    if tod == "evening":
        return "Алло, добрый вечер! Это голосовой ассистент поликлиники. Чем могу помочь?"
    return (
        "Алло, доброй ночи! Поликлиника закрыта, "
        "но я могу записать вас на приём. Чем могу помочь?"
    )