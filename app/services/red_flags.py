"""Детектор красных флагов по регламенту РГ-ТЕЛ-01, раздел 7.4.

Две категории:
    A — угроза жизни → R-01 → рекомендация 103/112 + перевод P1.
    B — острое состояние → R-11 → перевод регистратору P1.

Принципы (из регламента):
    - Распознавание работает по смыслу, а не только по точным словам.
    - При сомнении — считать флаг сработавшим (ложная тревога допустима).
    - Распознавание не является оценкой состояния — это правило безопасности.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.constants import (
    EMERGENCY_PHRASE,
    RED_FLAG_ALLERGY,
    RED_FLAG_BLEEDING,
    RED_FLAG_BREATHING,
    RED_FLAG_CATEGORY_A,
    RED_FLAG_CATEGORY_B,
    RED_FLAG_CHEST_PAIN,
    RED_FLAG_CHILD,
    RED_FLAG_CONSCIOUSNESS,
    RED_FLAG_HIGH_FEVER,
    RED_FLAG_MINOR_TRAUMA,
    RED_FLAG_PREGNANCY,
    RED_FLAG_SEIZURE,
    RED_FLAG_SELF_HARM,
    RED_FLAG_SEVERE_PAIN,
    RED_FLAG_STROKE,
    RED_FLAG_TRAUMA,
    RED_FLAG_WORSENING,
    URGENT_PHRASE,
)


@dataclass
class RedFlag:
    """Обнаруженный красный флаг."""

    category: str  # "A" или "B"
    group: str     # группа из раздела 7.4
    matched: str   # что именно сработало
    phrase: str    # что сказать пациенту


# ─────────────────────────────────────────────────────────────
# Паттерны категории А (угроза жизни)
# ─────────────────────────────────────────────────────────────

_CATEGORY_A: dict[str, list[re.Pattern[str]]] = {
    RED_FLAG_CHEST_PAIN: [
        re.compile(r"боль\s+в\s+груд", re.IGNORECASE),
        re.compile(r"давит\s+за\s+грудин", re.IGNORECASE),
        re.compile(r"давит\s+в\s+груд", re.IGNORECASE),
        re.compile(r"жжёт\s+в\s+груд|жжет\s+в\s+груд", re.IGNORECASE),
        re.compile(r"отдаёт\s+в\s+левую\s+руку|отдает\s+в\s+левую\s+руку", re.IGNORECASE),
        re.compile(r"сердечн\w+\s+приступ", re.IGNORECASE),
        re.compile(r"\bинфаркт", re.IGNORECASE),
    ],
    RED_FLAG_BREATHING: [
        re.compile(r"не\s+может\s+дышать", re.IGNORECASE),
        re.compile(r"задыха\w+", re.IGNORECASE),
        re.compile(r"синеет", re.IGNORECASE),
        re.compile(r"хрипит", re.IGNORECASE),
        re.compile(r"подавил\w*ся", re.IGNORECASE),
    ],
    RED_FLAG_CONSCIOUSNESS: [
        re.compile(r"потерял\s+сознани", re.IGNORECASE),
        re.compile(r"без\s+сознани", re.IGNORECASE),
        re.compile(r"не\s+приходит\s+в\s+себя", re.IGNORECASE),
        re.compile(r"не\s+могу\s+разбудить", re.IGNORECASE),
        re.compile(r"упал\s+в\s+обморок", re.IGNORECASE),
    ],
    RED_FLAG_STROKE: [
        re.compile(r"перекосил\w*\s+лиц", re.IGNORECASE),
        re.compile(r"отнял\w*с[яь]\s+(рука|нога|рук|ног)", re.IGNORECASE),
        re.compile(r"отнял\w*с[яь]", re.IGNORECASE),
        re.compile(r"не\s+может\s+говорить", re.IGNORECASE),
        re.compile(r"речь\s+невнятн", re.IGNORECASE),
        re.compile(r"онемел\w*\s+половин", re.IGNORECASE),
    ],
    RED_FLAG_SEIZURE: [
        re.compile(r"судорог", re.IGNORECASE),
        re.compile(r"трясёт|трясет", re.IGNORECASE),
        re.compile(r"припадок", re.IGNORECASE),
    ],
    RED_FLAG_BLEEDING: [
        re.compile(r"сильн\w+\s+кровотечени", re.IGNORECASE),
        re.compile(r"кровь\s+не\s+останавлива", re.IGNORECASE),
        re.compile(r"рвот\w+\s+кровь", re.IGNORECASE),
        re.compile(r"кровь\s+изо\s+рта", re.IGNORECASE),
    ],
    RED_FLAG_TRAUMA: [
        re.compile(r"\bДТП\b", re.IGNORECASE),
        re.compile(r"ударил\w*ся\s+голов", re.IGNORECASE),
        re.compile(r"упал\s+с\s+высот", re.IGNORECASE),
        re.compile(r"ожог\s+больш", re.IGNORECASE),
        re.compile(r"отравил\w*ся", re.IGNORECASE),
        re.compile(r"проглотил\w*\s+(таблет|хими)", re.IGNORECASE),
        re.compile(r"укусил\w*\s+змея", re.IGNORECASE),
    ],
    RED_FLAG_ALLERGY: [
        re.compile(r"отка\w+\s+горл|отёк\w*\s+горл|отек\w*\s+горл", re.IGNORECASE),
        re.compile(r"не\s+может\s+глотать", re.IGNORECASE),
        re.compile(r"анафилактическ\w+\s+шок", re.IGNORECASE),
    ],
    RED_FLAG_CHILD: [
        re.compile(r"младенец\s+вял", re.IGNORECASE),
        re.compile(r"грудн\w+\s+ребён|грудн\w+\s+ребен", re.IGNORECASE),
        re.compile(r"ребёнок\s+посинел|ребенок\s+посинел", re.IGNORECASE),
        re.compile(r"ребёнок\s+проглотил|ребенок\s+проглотил", re.IGNORECASE),
    ],
    RED_FLAG_PREGNANCY: [
        re.compile(r"беременн\w+.{0,30}кровотечени", re.IGNORECASE),
        re.compile(r"отошли\s+воды", re.IGNORECASE),
        re.compile(r"схватк", re.IGNORECASE),
    ],
    RED_FLAG_SELF_HARM: [
        re.compile(r"не\s+хочу\s+жить", re.IGNORECASE),
        re.compile(r"покончить\s+с\s+собой", re.IGNORECASE),
        re.compile(r"наглота\w+ся\s+таблеток", re.IGNORECASE),
        re.compile(r"угрожает\s+убить", re.IGNORECASE),
    ],
}

# ─────────────────────────────────────────────────────────────
# Паттерны категории Б (острое состояние)
# ─────────────────────────────────────────────────────────────

_CATEGORY_B: dict[str, list[re.Pattern[str]]] = {
    RED_FLAG_SEVERE_PAIN: [
        re.compile(r"очень\s+сильн\w+\s+боль", re.IGNORECASE),
        re.compile(r"невыносим\w+", re.IGNORECASE),
        re.compile(r"боль\s+усилива", re.IGNORECASE),
    ],
    RED_FLAG_HIGH_FEVER: [
        re.compile(r"температура\s+сорок", re.IGNORECASE),
        re.compile(r"температура\s+40", re.IGNORECASE),
        re.compile(r"температура\s+не\s+сбива", re.IGNORECASE),
        re.compile(r"температура\s+третий\s+день", re.IGNORECASE),
    ],
    RED_FLAG_WORSENING: [
        re.compile(r"стало\s+намного\s+хуже", re.IGNORECASE),
        re.compile(r"резко\s+поднялось\s+давлени", re.IGNORECASE),
        re.compile(r"кружится\s+голова.{0,20}не\s+могу\s+встать", re.IGNORECASE),
    ],
    RED_FLAG_MINOR_TRAUMA: [
        re.compile(r"подвернул\w*\s+ног", re.IGNORECASE),
        re.compile(r"порезал\w*ся\s+глубоко", re.IGNORECASE),
    ],
}


# ─────────────────────────────────────────────────────────────
# Публичная функция
# ─────────────────────────────────────────────────────────────


def detect(text: str) -> RedFlag | None:
    """Найти красный флаг в реплике пациента.

    Возвращает RedFlag или None, если ничего не найдено.

    Порядок проверки: сначала категория А (угроза жизни), потом Б.
    При сомнении — срабатывает первое совпадение.
    """
    if not text:
        return None

    # Категория А — приоритет выше
    for group, patterns in _CATEGORY_A.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return RedFlag(
                    category=RED_FLAG_CATEGORY_A,
                    group=group,
                    matched=match.group(0),
                    phrase=EMERGENCY_PHRASE,
                )

    # Категория Б
    for group, patterns in _CATEGORY_B.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return RedFlag(
                    category=RED_FLAG_CATEGORY_B,
                    group=group,
                    matched=match.group(0),
                    phrase=URGENT_PHRASE,
                )

    return None