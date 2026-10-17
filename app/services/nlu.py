"""Простой NLU-парсер на regex для MVP.

Извлекает из текста пациента:
    - intent      — «book», «cancel», «check», «greeting», «unknown»;
    - ФИО         — last_name, first_name;
    - дата рождения;
    - специальность;
    - желаемую дату визита;
    - желаемое время.

Ограничение MVP: без GigaChat, только регулярки. Этого достаточно для C-01.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os

from openai import AsyncOpenAI


# Специальности (из листа «Специальности» schedule.xlsx)
SPECIALTIES = [
    "терапевт",
    "педиатр",
    "кардиолог",
    "гастроэнтеролог",
    "невролог",
    "эндокринолог",
    "нефролог",
    "аллерголог-иммунолог",
    "дерматовенеролог",
    "лор",
    "офтальмолог",
    "пульмонолог",
    "ревматолог",
    "уролог",
    "хирург",
    "травматолог",
    "ортопед",
    "флеболог",
    "акушер-гинеколог",
    "гинеколог",
    "репродуктолог",
    "маммолог",
    "стоматолог-терапевт",
    "стоматолог-хирург",
    "стоматолог-ортопед",
    "ортодонт",
]

SPECIALTY_ALIASES: dict[str, str] = {
    "лoр": "лор",
    "лор-врач": "лор",
    "ухо-горло-нос": "лор",
    "гинеколог": "акушер-гинеколог",
    "стоматолог": "стоматолог-терапевт",
    "зубной": "стоматолог-терапевт",
    "глазной": "офтальмолог",
    "окулист": "офтальмолог",
    "сердечный": "кардиолог",
    "желудок": "гастроэнтеролог",
    "нервы": "невролог",
    "щитовидка": "эндокринолог",
    "почки": "нефролог",
    "аллергия": "аллерголог-иммунолог",
    "кожа": "дерматовенеролог",
    "легкие": "пульмонолог",
    "суставы": "ревматолог",
    "хирург": "хирург",
    "перелом": "травматолог",
    "спина": "ортопед",
    "вены": "флеболог",
    "беременность": "акушер-гинеколог",
    "ребенок": "педиатр",
    "ребёнок": "педиатр",
    "дети": "педиатр",
}


# Модель
@dataclass
class ParsedUtterance:
    """Разобранная реплика пациента."""

    intent: str = "unknown"
    last_name: str | None = None
    first_name: str | None = None
    birth_date: str | None = None
    specialty: str | None = None
    desired_date: str | None = None
    desired_time: str | None = None
    raw_text: str = ""
    extra: dict = field(default_factory=dict)


# Регулярки
_RE_GREETING = re.compile(
    r"\b(здравствуйте|добрый\s+(день|вечер|утро)|привет|алло|доброе\s+утро)\b",
    re.IGNORECASE,
)

_RE_BOOK = re.compile(
    r"\b(запиш|записа|хочу\s+к|нужно\s+к|можно\s+к|талон|приём|прием)\w*",
    re.IGNORECASE,
)

_RE_CANCEL = re.compile(
    r"\b(отмен|не\s+приду|не\s+смогу)\w*",
    re.IGNORECASE,
)

_RE_CHECK = re.compile(
    r"\b(провер|узнать|когда\s+моя\s+запись|моя\s+запись|статус)\w*",
    re.IGNORECASE,
)

# ФИО: «Иванов Пётр» или «Пётр Иванов»
_RE_NAME_DIRECT = re.compile(
    r"\b([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)\b",
)

# Дата рождения: 17.03.1985 или 17 марта 1985
_RE_BIRTH_NUM = re.compile(
    r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b",
)
_RE_BIRTH_TEXT = re.compile(
    r"\b(\d{1,2})\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*\s+(\d{4})\b",
    re.IGNORECASE,
)

# Дата визита: 20.10.2026
_RE_DATE_NUM = re.compile(
    r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b",
)

# Время: 10:30, в 10, в 10 утра, в половине одиннадцатого
_RE_TIME = re.compile(
    r"\b(?:в\s+)?(\d{1,2})[:.](\d{2})\b|\bв\s+(\d{1,2})\s*(?:час|утра|дня|вечера)\b",
    re.IGNORECASE,
)

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
    "май": 5, "мая": 5, "июн": 6, "июл": 7,
    "август": 8, "сентябр": 9, "октябр": 10,
    "ноябр": 11, "декабр": 12,
}

_RELATIVE_DAYS = {
    "завтра": 1,
    "послезавтра": 2,
    "сегодня": 0,
}


# ─────────────────────────────────────────────────────────────
# NLU через GigaChat
# ─────────────────────────────────────────────────────────────

_MODEL_NAME = "ai-sage/GigaChat3-10B-A1.8B"

_llm_client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=10.0,
)

_SYSTEM_PROMPT = (
    "Ты — парсер реплик пациента поликлиники. "
    "Извлеки из текста: intent (book/cancel/check/greeting/unknown), "
    "specialty (терапевт, педиатр, лор, кардиолог, невролог, хирург, "
    "офтальмолог, гинеколог, стоматолог, эндокринолог, уролог и т.д.), "
    "last_name, first_name, birth_date (строго ДД.ММ.ГГГГ). "
    "Понимай синонимы: «к ушам горлу носу» → лор, «сердечный врач» → кардиолог, "
    "«зубной» → стоматолог. "
    "Верни ТОЛЬКО валидный JSON без markdown и пояснений. "
    'Пример: {"intent": "book", "specialty": "лор"}'
)


async def parse(text: str, today: str) -> ParsedUtterance:
    """NLU: GigaChat для интентов/специальностей, regex для ФИО и дат."""
    # 1. Всегда парсим regex — он надёжен для ФИО и дат
    regex_result = _parse_with_regex(text, today)

    # 2. Если нет ключа — возвращаем regex
    if not os.getenv("OPENAI_API_KEY"):
        return regex_result

    # 3. Спрашиваем GigaChat — он лучше понимает синонимы
    try:
        response = await _llm_client.chat.completions.create(
            model=_MODEL_NAME,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        raw = (response.choices[0].message.content or "{}").strip()
        raw = raw.removeprefix("```json").removeprefix("```")
        raw = raw.removesuffix("```").strip()
        data = json.loads(raw)

        # 4. Мёржим: LLM приоритет для интента/специальности,
        #    regex приоритет для ФИО и даты рождения
        return ParsedUtterance(
            intent=data.get("intent") or regex_result.intent,
            specialty=data.get("specialty") or regex_result.specialty,
            last_name=data.get("last_name") or regex_result.last_name,
            first_name=data.get("first_name") or regex_result.first_name,
            birth_date=data.get("birth_date") or regex_result.birth_date,
            raw_text=text,
        )
    except Exception:  # noqa: BLE001
        return regex_result
    

# Парсер
def _parse_with_regex(text: str, today: str) -> ParsedUtterance:
    """Разобрать реплику пациента.

    Аргументы:
        text: сырая реплика.
        today: «сегодня» в формате ДД.ММ.ГГГГ (для относительных дат).
    """
    result = ParsedUtterance(raw_text=text)
    lowered = text.lower()

    # Интент
    if _RE_CANCEL.search(lowered):
        result.intent = "cancel"
    elif _RE_CHECK.search(lowered):
        result.intent = "check"
    elif _RE_BOOK.search(lowered):
        result.intent = "book"
    elif _RE_GREETING.search(lowered):
        result.intent = "greeting"

    # Специальность
    spec = _extract_specialty(lowered)
    if spec:
        result.specialty = spec

    # ФИО
    name = _extract_name(text)
    if name:
        result.last_name, result.first_name = name

    # Дата рождения
    birth = _extract_birth_date(text)
    if birth:
        result.birth_date = birth

    # Дата визита (не путать с датой рождения)
    desired = _extract_desired_date(text, today, exclude=result.birth_date)
    if desired:
        result.desired_date = desired

    # Время
    time = _extract_time(text)
    if time:
        result.desired_time = time

    return result


def _extract_specialty(lowered: str) -> str | None:
    # Сначала точные названия
    for spec in SPECIALTIES:
        if spec in lowered:
            return spec.capitalize()
    # Потом алиасы
    for alias, spec in SPECIALTY_ALIASES.items():
        if alias in lowered:
            return spec.capitalize()
    return None


def _extract_name(text: str) -> tuple[str, str] | None:
    """Извлечь «Фамилия Имя» из текста. Эвристика: оба слова с большой буквы."""
    matches = _RE_NAME_DIRECT.findall(text)
    if not matches:
        return None
    # Ищем пару, где второе слово похоже на имя (не специальность)
    for last, first in matches:
        last_low = last.lower()
        first_low = first.lower()
        if last_low in SPECIALTIES or first_low in SPECIALTIES:
            continue
        if last_low in SPECIALTY_ALIASES or first_low in SPECIALTY_ALIASES:
            continue
        return last, first
    return None


def _extract_birth_date(text: str) -> str | None:
    # Числовой формат
    m = _RE_BIRTH_NUM.search(text)
    if m:
        d, mo, y = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).strftime("%d.%m.%Y")
        except ValueError:
            return None

    # Текстовый формат
    m = _RE_BIRTH_TEXT.search(text)
    if m:
        d, month_name, y = m.groups()
        month = _MONTHS.get(month_name.lower()[:5])
        if month:
            try:
                return datetime(int(y), month, int(d)).strftime("%d.%m.%Y")
            except ValueError:
                return None
    return None


def _extract_desired_date(
    text: str, today: str, exclude: str | None = None
) -> str | None:
    lowered = text.lower()

    # Относительные
    for word, offset in _RELATIVE_DAYS.items():
        if word in lowered:
            base = datetime.strptime(today, "%d.%m.%Y")
            return (base + timedelta(days=offset)).strftime("%d.%m.%Y")

    # Числовые — но не та же, что дата рождения
    for m in _RE_DATE_NUM.finditer(text):
        d, mo, y = m.groups()
        try:
            candidate = datetime(int(y), int(mo), int(d)).strftime("%d.%m.%Y")
        except ValueError:
            continue
        if exclude and candidate == exclude:
            continue
        if candidate == today:
            continue
        return candidate

    return None


def _extract_time(text: str) -> str | None:
    m = _RE_TIME.search(text)
    if not m:
        return None
    hh, mm, hh_only = m.groups()
    if hh and mm:
        try:
            return f"{int(hh):02d}:{int(mm):02d}"
        except ValueError:
            return None
    if hh_only:
        try:
            return f"{int(hh_only):02d}:00"
        except ValueError:
            return None
    return None