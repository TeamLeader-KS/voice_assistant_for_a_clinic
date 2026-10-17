# Коды результатов звонка (Приложение Г регламента)
BOOKED = "BOOKED"
BOOKED_GP = "BOOKED_GP"
BOOKED_PAID = "BOOKED_PAID"
RESCHEDULED = "RESCHEDULED"
CANCELLED = "CANCELLED"
CONFIRMED = "CONFIRMED"
INFO_GIVEN = "INFO_GIVEN"
WAITLISTED = "WAITLISTED"
HOME_VISIT_REQUESTED = "HOME_VISIT_REQUESTED"
ESCALATED = "ESCALATED"
CALLBACK = "CALLBACK"
EMERGENCY = "EMERGENCY"
COMPLAINT = "COMPLAINT"
GRATITUDE = "GRATITUDE"
DROPPED = "DROPPED"

# Приоритеты переводов (раздел 7.5)
P1_EMERGENCY = "P1"
P2_HIGH = "P2"
P3_NORMAL = "P3"


# Красные флаги (раздел 7.4 регламента РГ-ТЕЛ-01)

# Категории
RED_FLAG_CATEGORY_A = "A"  # Угроза жизни → R-01 → 103/112 + P1
RED_FLAG_CATEGORY_B = "B"  # Острое состояние → R-11 → регистратор P1

# Группы категории А
RED_FLAG_CHEST_PAIN = "боль_в_груди"
RED_FLAG_BREATHING = "нарушение_дыхания"
RED_FLAG_CONSCIOUSNESS = "потеря_сознания"
RED_FLAG_STROKE = "инсульт"
RED_FLAG_SEIZURE = "судороги"
RED_FLAG_BLEEDING = "кровотечение"
RED_FLAG_TRAUMA = "травма_отравление"
RED_FLAG_ALLERGY = "аллергия"
RED_FLAG_CHILD = "ребёнок"
RED_FLAG_PREGNANCY = "беременность"
RED_FLAG_SELF_HARM = "угроза_себе_или_другим"

# Группы категории Б
RED_FLAG_SEVERE_PAIN = "острая_боль"
RED_FLAG_HIGH_FEVER = "высокая_температура"
RED_FLAG_WORSENING = "резкое_ухудшение"
RED_FLAG_MINOR_TRAUMA = "травма_без_угрозы"

# Номера экстренных служб
EMERGENCY_PHONE_SHORT = "103"
EMERGENCY_PHONE_UNIFIED = "112"

# Фраза-скрипт для категории А (эталон из С-14)
EMERGENCY_PHRASE = (
    "Пожалуйста, немедленно звоните в скорую помощь: сто три или сто двенадцать. "
    "Повторяю: сто три или сто двенадцать. Не ждите приёма в поликлинике."
)

# Фраза-скрипт для категории Б
URGENT_PHRASE = (
    "Соединяю с регистратором, он организует срочную помощь. "
    "Если станет хуже — сразу звоните сто три."
)