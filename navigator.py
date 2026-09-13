#!/usr/bin/env python3
"""
Навигатор Успеха v3.4
Чат-бот для школьников (5-9 класс)
Конкурс «Технологии Первых» 2026

Что умеет:
- ИИ-тьютор (GigaChat) — объясняет конкретные темы простыми словами
- Расписание на неделю с авто-напоминаниями за 15 минут
- Свои напоминания (за 30 и 15 минут)
- ЦОК: выбор предмета → «Объяснить тему» или «Ресурсы»
- Утренняя мотивация (07:30) и вечерний совет (21:00) — автоматически
- Домашние задания, оценки, анализ нагрузки
- Геймификация — баллы и уровни
"""

import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# ═══════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════

TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    raise RuntimeError("VK_TOKEN не найден! Добавь переменную окружения VK_TOKEN в панели Bothost.")

GIGA_KEY = os.getenv("GIGA_KEY", "")
DATA_FILE = "navigator_data.json"

# Время рассылки (МСК)
MORNING_HOUR, MORNING_MIN = 7, 30
EVENING_HOUR, EVENING_MIN = 21, 0

# ═══════════════════════════════════════════
#  ПРЕДМЕТЫ ПО КЛАССАМ
# ═══════════════════════════════════════════

GRADE_SUBJECTS = {
    "5 класс": [
        "Математика", "Русский язык", "Литература", "Английский язык",
        "История", "Биология", "География", "Обществознание",
        "Информатика", "Музыка", "ИЗО", "Технология", "Физкультура", "ОБЖ",
        "Разговоры о важном", "Мои горизонты", "Финансовая грамотность",
    ],
    "6 класс": [
        "Математика", "Русский язык", "Литература", "Английский язык",
        "История", "Биология", "География", "Обществознание",
        "Информатика", "Музыка", "ИЗО", "Технология", "Физкультура", "ОБЖ",
        "Разговоры о важном", "Мои горизонты", "Финансовая грамотность",
    ],
    "7 класс": [
        "Алгебра", "Геометрия", "Русский язык", "Литература",
        "Английский язык", "История", "Обществознание", "Биология",
        "География", "Физика", "Информатика", "Музыка", "ИЗО",
        "Технология", "Физкультура", "ОБЖ",
        "Разговоры о важном", "Мои горизонты", "Финансовая грамотность",
    ],
    "8 класс": [
        "Алгебра", "Геометрия", "Русский язык", "Литература",
        "Английский язык", "История", "Обществознание", "Биология",
        "География", "Физика", "Химия", "Информатика",
        "ИЗО", "Технология", "Физкультура", "ОБЖ",
        "Разговоры о важном", "Мои горизонты", "Финансовая грамотность",
    ],
    "9 класс": [
        "Алгебра", "Геометрия", "Русский язык", "Литература",
        "Английский язык", "История", "Обществознание", "Биология",
        "География", "Физика", "Химия", "Информатика",
        "Физкультура", "ОБЖ",
        "Разговоры о важном", "Мои горизонты", "Финансовая грамотность",
    ],
}

EXTRA_ACTIVITIES = [
    "🎵 Музыкальная школа", "⚽ Спортивная секция", "📚 Репетитор",
    "🎭 Репетиция", "💃 Танцы", "🎨 Изостудия", "♟️ Шахматы", "➕ Другое",
]

# ═══════════════════════════════════════════
#  ДНИ НЕДЕЛИ
# ═══════════════════════════════════════════

DAYS_RU = {
    "monday": "Понедельник", "tuesday": "Вторник", "wednesday": "Среда",
    "thursday": "Четверг", "friday": "Пятница", "saturday": "Суббота",
    "sunday": "Воскресенье",
}
DAYS_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_NAME_TO_KEY = {v.lower(): k for k, v in DAYS_RU.items()}

WEEKDAY_ALIASES = {
    "понедельник": 0, "пн": 0,
    "вторник": 1, "вт": 1,
    "среда": 2, "среду": 2, "ср": 2,
    "четверг": 3, "чт": 3,
    "пятница": 4, "пятницу": 4, "пт": 4,
    "суббота": 5, "субботу": 5, "сб": 5,
    "воскресенье": 6, "воскресение": 6, "вс": 6, "воскр": 6,
}

# ═══════════════════════════════════════════
#  ВРЕМЕННЫЕ СЛОТЫ (под школу)
#  Уроки по 45 мин, перемены: 15, 10, 20, 20, 15, 10, 5
# ═══════════════════════════════════════════

TIMES = [
    "08:30",  # 1 урок
    "09:30",  # 2 урок (перемена 15)
    "10:25",  # 3 урок (перемена 10)
    "11:30",  # 4 урок (перемена 20)
    "12:35",  # 5 урок (перемена 20)
    "13:35",  # 6 урок (перемена 15)
    "14:30",  # 7 урок (перемена 10)
    "15:20",  # 8 урок (перемена 5)
    # Внеклассные слоты
    "16:00", "16:45", "17:30", "18:15", "19:00",
]

# ═══════════════════════════════════════════
#  КАТЕГОРИИ ПРЕДМЕТОВ ДЛЯ ЦОК
# ═══════════════════════════════════════════

SUBJECT_CATEGORIES = {
    "Основные": ["Математика", "Алгебра", "Геометрия", "Русский язык",
                 "Литература", "Английский язык"],
    "Естественные": ["Физика", "Химия", "Биология", "География", "Информатика"],
    "Гуманитарные": ["История", "Обществознание"],
    "Творчество и спорт": ["ИЗО", "Музыка", "Технология", "Физкультура", "ОБЖ"],
    "Важное и новое": ["Разговоры о важном", "Мои горизонты",
                      "Финансовая грамотность"],
}

# ═══════════════════════════════════════════
#  РЕСУРСЫ ПО ПРЕДМЕТАМ (ЦОК вместо РЭШ)
# ═══════════════════════════════════════════

SUBJECT_RESOURCES = {
    "Математика": [
        "📐 ЦОК (ФГИС «Моя школа») — библиотека цифрового контента по математике",
        "📐 Учи.ру — uchi.ru",
        "📐 Яндекс.Учебник — education.yandex.ru",
        "📐 Stepik (курсы) — stepik.org",
    ],
    "Алгебра": [
        "📐 ЦОК — библиотека цифрового контента по алгебре",
        "📐 Фоксфорд.Учебник — foxford.ru",
        "📐 Stepik — stepik.org",
    ],
    "Геометрия": [
        "📐 ЦОК — библиотека цифрового контента по геометрии",
        "📐 Фоксфорд.Учебник — foxford.ru",
        "📐 Stepik — stepik.org",
    ],
    "Русский язык": [
        "📖 ЦОК — библиотека цифрового контента по русскому языку",
        "📖 Грамота.ру — gramota.ru",
        "📖 Яндекс.Учебник — education.yandex.ru",
    ],
    "Литература": [
        "📚 ЦОК — библиотека цифрового контента по литературе",
        "📚 Фоксфорд.Учебник — foxford.ru",
        "📚 Литература.ИНФО — lit-info.ru",
    ],
    "Английский язык": [
        "🇬🇧 Учи.ру — uchi.ru",
        "🇬🇧 ЦОК — библиотека цифрового контента по английскому",
        "🇬🇧 Stepik — stepik.org",
        "🇬🇧 Lingualeo — lingualeo.com",
    ],
    "История": [
        "🏛 ЦОК — библиотека цифрового контента по истории",
        "🏛 Фоксфорд.Учебник — foxford.ru",
        "🏛 История.РФ — histrf.ru",
    ],
    "Обществознание": [
        "🏛 ЦОК — библиотека цифрового контента по обществознанию",
        "🏛 Фоксфорд.Учебник — foxford.ru",
        "🏛 Stepik — stepik.org",
    ],
    "Биология": [
        "🧬 ЦОК — библиотека цифрового контента по биологии",
        "🧬 Учи.ру — uchi.ru",
        "🧬 Stepik — stepik.org",
    ],
    "География": [
        "🌍 ЦОК — библиотека цифрового контента по географии",
        "🌍 Учи.ру — uchi.ru",
    ],
    "Физика": [
        "⚛ ЦОК — библиотека цифрового контента по физике",
        "⚛ Фоксфорд.Учебник — foxford.ru",
        "⚛ Stepik — stepik.org",
    ],
    "Химия": [
        "🧪 ЦОК — библиотека цифрового контента по химии",
        "🧪 Фоксфорд.Учебник — foxford.ru",
        "🧪 Stepik — stepik.org",
    ],
    "Информатика": [
        "💻 ЦОК — библиотека цифрового контента по информатике",
        "💻 Stepik — stepik.org",
        "💻 КЕГЭ — kge.rustest.ru",
        "💻 Питонтьютор — pythontutor.ru",
    ],
    "Музыка": ["🎵 ЦОК — библиотека цифрового контента по музыке"],
    "ИЗО": ["🎨 ЦОК — библиотека цифрового контента по ИЗО"],
    "Технология": ["🔧 ЦОК — библиотека цифрового контента по технологии"],
    "Физкультура": ["⚽ ЦОК — библиотека цифрового контента по физкультуре"],
    "ОБЖ": ["🛡 ЦОК — библиотека цифрового контента по ОБЖ"],
    "Разговоры о важном": ["💬 ЦОК — материалы для «Разговоров о важном»"],
    "Мои горизонты": [
        "🔮 ЦОК — тематические материалы",
        "🔮 Билет в будущее — bvbinfo.ru",
    ],
    "Финансовая грамотность": [
        "💰 ЦОК — материалы по финансовой грамотности",
        "💰 Финкульт.инфо — finkult.info",
        "💰 Stepik — stepik.org",
    ],
}

# ═══════════════════════════════════════════
#  СЛОЖНОСТЬ ПРЕДМЕТОВ (для анализа нагрузки)
# ═══════════════════════════════════════════

SUBJECT_DIFFICULTY = {
    "Математика": 3, "Алгебра": 3, "Геометрия": 3, "Физика": 3, "Химия": 3,
    "Русский язык": 2, "Литература": 2, "Английский язык": 2, "История": 2,
    "Обществознание": 2, "Биология": 2, "География": 1, "Информатика": 2,
    "Музыка": 1, "ИЗО": 1, "Технология": 1, "Физкультура": 1, "ОБЖ": 1,
    "Разговоры о важном": 1, "Мои горизонты": 1, "Финансовая грамотность": 2,
}

# ═══════════════════════════════════════════
#  МОТИВАЦИЯ И СОВЕТЫ
# ═══════════════════════════════════════════

MORNING_QUOTES = [
    "☀️ Доброе утро, навигатор! Сегодня отличный день, чтобы узнать что-то новое. Пусть всё получается! 🎯",
    "🌞 Ты уже на шаг ближе к цели. Пусть день будет продуктивным и интересным! 📚",
    "✨ Сегодня ты можешь сделать что-то важное. Верь в себя — у тебя всё выйдет! 💪",
    "🌅 Утро — время новых возможностей. Начни день с улыбки и пары полезных дел! 😊",
    "🚀 День начинается! Пусть каждая маленькая победа радует, а сложности делают сильнее.",
]

EVENING_QUOTES = [
    "🌙 Вечер — время выдохнуть и подвести итоги. Ты сегодня много сделал — это ценно. 😌",
    "🌘 День был насыщенным. Отдохни, наберись сил — завтра снова в путь! 😴",
    "🌟 Ты молодец! Даже если что-то не получилось — ты старался. Это главное. 🤗",
    "🌑 Пусть вечер будет спокойным и уютным. Завтра будет новый день и новые возможности. ☕",
    "💫 Ты прошёл ещё один день. Пусть ночь подарит отдых, а утро — вдохновение! ✨",
]

STUDY_TIPS = [
    "💡 Совет: читай учебник с карандашом — отмечай главное прямо в тексте.",
    "💡 Совет: объясни новую тему кому-то — так ты поймёшь её лучше.",
    "💡 Совет: 25 минут работы, 5 отдыха — техника Pomodoro. Попробуй!",
    "💡 Совет: повторяй материал перед сном — мозг запоминает лучше.",
    "💡 Совет: составляй план на день с вечера — так утром легче начать.",
    "💡 Совет: делай самые сложные задачи первыми, пока есть энергия.",
]

# ═══════════════════════════════════════════
#  УРОВНИ ГЕЙМИФИКАЦИИ
# ═══════════════════════════════════════════

LEVELS = [
    (0,    "🌱 Новичок"),
    (50,   "📚 Ученик"),
    (150,  "🎓 Знаток"),
    (300,  "🏆 Навигатор знаний"),
    (500,  "⭐ Магистр знаний"),
]

def get_level(points):
    name = LEVELS[0][1]
    threshold = LEVELS[0][0]
    for lvl_points, lvl_name in LEVELS:
        if points >= lvl_points:
            name = lvl_name
            threshold = lvl_points
    next_level = None
    for lvl_points, lvl_name in LEVELS:
        if points < lvl_points:
            next_level = (lvl_points, lvl_name)
            break
    return name, threshold, next_level

# ═══════════════════════════════════════════
#  ПРИМЕРЫ ТЕМ ДЛЯ ПОДСКАЗОК В ЦОК
# ═══════════════════════════════════════════

TOPIC_EXAMPLES = {
    "Математика": "«дроби», «деление в столбик», «проценты», «уравнения»",
    "Алгебра": "«линейные уравнения», «формулы сокращённого умножения», «степени»",
    "Геометрия": "«теорема Пифагора», «признаки равенства треугольников», «площадь»",
    "Русский язык": "«приставки ПРЕ и ПРИ», «спряжения глаголов», «обособленные определения»",
    "Литература": "«образ Печорина», «эпитеты и метафоры», «композиция рассказа»",
    "Английский язык": "«Present Simple», «модальные глаголы», «артикли»",
    "История": "«реформы Петра I», «Древняя Русь», «отмена крепостного права»",
    "Обществознание": "«виды власти», «инфляция», «права человека»",
    "Биология": "«фотосинтез», «строение клетки», «кровообращение»",
    "География": "«климатические пояса», «формы рельефа», «океанические течения»",
    "Физика": "«закон Ома», «инерция», «электрическая цепь»",
    "Химия": "«валентность», «реакции замещения», «периодический закон»",
    "Информатика": "«алгоритмы», «циклы», «двоичная система»",
    "Финансовая грамотность": "«бюджет семьи», «вклады», «налоги»",
    "Разговоры о важном": "«эмоции», «общение», «дружба»",
    "Мои горизонты": "«профессии», «цели», «самопознание»",
}

TOPIC_EXAMPLES_SHORT = {
    "Математика": "«дроби», «проценты»",
    "Алгебра": "«формулы сокращённого умножения»",
    "Геометрия": "«теорема Пифагора»",
    "Русский язык": "«приставки ПРЕ и ПРИ»",
    "Литература": "«образ Печорина»",
    "Английский язык": "«Present Simple»",
    "История": "«реформы Петра I»",
    "Обществознание": "«виды власти»",
    "Биология": "«фотосинтез»",
    "География": "«климатические пояса»",
    "Физика": "«закон Ома»",
    "Химия": "«валентность»",
    "Информатика": "«циклы»",
    "Финансовая грамотность": "«бюджет семьи»",
    "Разговоры о важном": "«эмоции»",
    "Мои горизонты": "«профессии»",
}

# ═══════════════════════════════════════════
#  ИИ-ТЬЮТОР (GigaChat)
# ═══════════════════════════════════════════

def ai_explain(topic, grade="", subject=""):
    if not GIGA_KEY:
        return ("🤖 ИИ-тьютор пока не подключён. "
                "Чтобы включить, получи бесплатный ключ GigaChat "
                "на developers.sber.ru и добавь в переменную GIGA_KEY.")
    try:
        from gigachat import GigaChat
        grade_hint = f"Ученик учится в {grade}." if grade else "Ученик 5-9 класса."
        subject_hint = f"Предмет: {subject}. " if subject else ""
        system_prompt = (
            f"Ты — дружелюбный школьный тьютор. {grade_hint} "
            f"{subject_hint}"
            "Школьник просит объяснить КОНКРЕТНУЮ ТЕМУ — не предмет в целом, "
            "а конкретную тему внутри него. "
            "Объясни эту тему ПРОСТЫМИ словами, с примерами из жизни. "
            "НЕ давай готовые ответы на домашние задания — подводи к пониманию. "
            "НЕ объясняй что такое предмет в целом — объясняй конкретную тему. "
            "В конце задай ОДИН проверочный вопрос по теме. "
            "Ответ — не больше 150 слов."
        )
        user_content = (f"По предмету «{subject}» объясни тему: {topic}"
                        if subject else f"Объясни тему: {topic}")
        with GigaChat(credentials=GIGA_KEY, verify_ssl_certs=False) as giga:
            response = giga.chat({
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            })
            return response.choices[0].message.content
    except ImportError:
        return "🤖 Библиотека gigachat не установлена. Напиши: pip install gigachat"
    except Exception as e:
        return f"🤖 ИИ-тьютор временно недоступен. Попробуй позже! ({str(e)[:50]})"

# ═══════════════════════════════════════════
#  ПАРСИНГ ДАТЫ/ВРЕМЕНИ ДЛЯ НАПОМИНАНИЙ
# ═══════════════════════════════════════════

def parse_reminder_datetime(text):
    text = text.strip().lower().replace("в ", " ")
    now = datetime.now()

    relative = {"сегодня": 0, "сегодняшн": 0, "завтра": 1, "послезавтра": 2}
    for keyword, delta_days in relative.items():
        if text.startswith(keyword):
            rest = text[len(keyword):].strip()
            time_str = _extract_time(rest)
            if time_str:
                target = now + timedelta(days=delta_days)
                return _make_dt(target, time_str)
            return None

    for alias, weekday_num in WEEKDAY_ALIASES.items():
        if text.startswith(alias):
            rest = text[len(alias):].strip()
            time_str = _extract_time(rest)
            if time_str:
                target = now
                days_ahead = weekday_num - target.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                target = target + timedelta(days=days_ahead)
                return _make_dt(target, time_str)
            return None

    m = re.match(r'^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})', text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        hour = int(m.group(4))
        minute = int(m.group(5))
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None

    m = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    return None

def _extract_time(text):
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if m:
        return m.group(0)
    return None

def _make_dt(base_date, time_str):
    h, m = map(int, time_str.split(":"))
    return base_date.replace(hour=h, minute=m, second=0, microsecond=0)

def format_dt(dt):
    return dt.strftime("%d.%m в %H:%M")

# ═══════════════════════════════════════════
#  ХРАНИЛИЩЕ ДАННЫХ
# ═══════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "schedules": {},
        "reminders_on": {},
        "custom_reminders": {},
        "homework": {},
        "grades": {},
        "points": {},
        "ai_history": {},
        "sent_morning": {},
        "sent_evening": {},
    }

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)

DATA = load_data()
sent_reminders = {}

# ═══════════════════════════════════════════
#  ГЕЙМИФИКАЦИЯ
# ═══════════════════════════════════════════

def add_points(uid_s, amount, reason=""):
    points = DATA.setdefault("points", {}).get(uid_s, 0) + amount
    DATA["points"][uid_s] = points
    save_data()
    return points

def points_info(uid_s):
    points = DATA.get("points", {}).get(uid_s, 0)
    name, threshold, next_level = get_level(points)
    info = f"🎯 Твой уровень: {name}\n🏅 Баллов: {points}"
    if next_level:
        need = next_level[0] - points
        info += f"\nДо «{next_level[1]}»: {need} баллов"
    return info

# ═══════════════════════════════════════════
#  АНАЛИЗ НАГРУЗКИ
# ═══════════════════════════════════════════

def analyze_week(uid_s):
    week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
    if not week:
        return "Расписание не настроено. Сначала добавь уроки!"
    day_scores = {}
    for day_key in DAYS_ORDER:
        items = week.get(day_key, [])
        score = sum(SUBJECT_DIFFICULTY.get(item.get("subject", ""), 2)
                     for item in items if item.get("type") == "lesson")
        extras = sum(1 for item in items if item.get("type") == "extra")
        day_scores[day_key] = {"lessons": len(items), "difficulty": score, "extras": extras}
    hardest = max(day_scores.items(), key=lambda x: x[1]["difficulty"])
    easiest = min(day_scores.items(), key=lambda x: x[1]["difficulty"])
    lines = ["📊 Анализ недели:\n"]
    for day_key in DAYS_ORDER:
        if day_key not in day_scores:
            continue
        info = day_scores[day_key]
        bar = "█" * min(info["difficulty"], 10)
        lines.append(f"  {DAYS_RU[day_key]}: {bar} ({info['lessons']} уроков"
                     + (f", +{info['extras']} кружков" if info["extras"] else "")
                     + ")")
    lines.append("")
    if hardest[1]["difficulty"] >= 8:
        lines.append(f"⚠️ Самый тяжёлый день — {DAYS_RU[hardest[0]]}.")
        lines.append("💡 Совет: готовься к нему заранее.")
        if easiest[1]["difficulty"] <= 3 and easiest[0] != hardest[0]:
            lines.append(f"  В {DAYS_RU[easiest[0]]} меньше нагрузки — займись подготовкой.")
    else:
        lines.append("✅ Нагрузка распределена равномерно. Так держать!")
    return "\n".join(lines)

# ═══════════════════════════════════════════
#  ТРЕКИНГ ПРОГРЕССА
# ═══════════════════════════════════════════

def track_topic(uid_s, topic, subject=""):
    DATA.setdefault("ai_history", {}).setdefault(uid_s, []).append({
        "topic": topic,
        "subject": subject,
        "date": datetime.now().strftime("%d.%m"),
    })
    save_data()

def progress_report(uid_s):
    history = DATA.get("ai_history", {}).get(uid_s, [])
    if not history:
        return "Ты ещё не спрашивал у ИИ-тьютора. Напиши «Объясни тему: ...», и я начну отслеживать!"
    topic_count = {}
    for entry in history:
        label = entry["topic"].lower()
        if entry.get("subject"):
            label = f"{entry['subject']}: {entry['topic']}".lower()
        topic_count[label] = topic_count.get(label, 0) + 1
    lines = ["📈 Карта твоих запросов:\n"]
    for topic, count in sorted(topic_count.items(), key=lambda x: -x[1]):
        bars = "▓" * min(count, 10)
        lines.append(f"  {topic}: {bars} ({count} раз)")
    top_topic = max(topic_count.items(), key=lambda x: x[1])
    if top_topic[1] >= 3:
        lines.append(f"\n💡 Ты спрашивал про «{top_topic[0]}» уже {top_topic[1]} раз.")
        lines.append("Давай закрепим! Напиши эту тему ещё раз — я дам проверочный вопрос.")
    else:
        lines.append("\n✅ Пока всё под контролем!")
    return "\n".join(lines)

# ═══════════════════════════════════════════
#  ВСЕ ПРЕДМЕТЫ (для проверки кликов)
# ═══════════════════════════════════════════

ALL_SUBJECTS = set()
for subs in GRADE_SUBJECTS.values():
    ALL_SUBJECTS.update(subs)
for subs in SUBJECT_CATEGORIES.values():
    ALL_SUBJECTS.update(subs)

# ═══════════════════════════════════════════
#  КЛАВИАТУРЫ
# ═══════════════════════════════════════════

def build_keyboard(rows, one_time=False):
    kb = VkKeyboard(one_time=one_time)
    for row_idx, row in enumerate(rows):
        for label, color in row:
            kb.add_button(label, color=color)
        if row_idx < len(rows) - 1:
            kb.add_line()
    return kb.get_keyboard()

def main_keyboard():
    return build_keyboard([
        [("📅 Расписание", VkKeyboardColor.PRIMARY),
         ("📝 Домашка", VkKeyboardColor.PRIMARY)],
        [("🤖 ИИ-тьютор", VkKeyboardColor.POSITIVE),
         ("⏰ Напоминания", VkKeyboardColor.PRIMARY)],
        [("🏆 Оценки", VkKeyboardColor.POSITIVE),
         ("📊 Анализ недели", VkKeyboardColor.POSITIVE)],
        [("📈 Мой прогресс", VkKeyboardColor.PRIMARY),
         ("🎯 Мой уровень", VkKeyboardColor.PRIMARY)],
        [("📚 Учёба (ЦОК)", VkKeyboardColor.PRIMARY),
         ("ℹ️ Помощь", VkKeyboardColor.SECONDARY)],
    ])

def schedule_menu_keyboard():
    return build_keyboard([
        [("⚙️ Настроить расписание", VkKeyboardColor.PRIMARY)],
        [("📋 На сегодня", VkKeyboardColor.PRIMARY),
         ("📋 На неделю", VkKeyboardColor.PRIMARY)],
        [("🗑 Очистить расписание", VkKeyboardColor.NEGATIVE)],
        [("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def grade_keyboard():
    return build_keyboard([
        [("5 класс", VkKeyboardColor.PRIMARY), ("6 класс", VkKeyboardColor.PRIMARY)],
        [("7 класс", VkKeyboardColor.PRIMARY), ("8 класс", VkKeyboardColor.PRIMARY)],
        [("9 класс", VkKeyboardColor.PRIMARY)],
        [("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def day_keyboard():
    return build_keyboard([
        [("Понедельник", VkKeyboardColor.PRIMARY), ("Вторник", VkKeyboardColor.PRIMARY)],
        [("Среда", VkKeyboardColor.PRIMARY), ("Четверг", VkKeyboardColor.PRIMARY)],
        [("Пятница", VkKeyboardColor.PRIMARY), ("Суббота", VkKeyboardColor.PRIMARY)],
        [("Воскресенье", VkKeyboardColor.PRIMARY)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])

def sched_type_keyboard():
    return build_keyboard([
        [("📖 Школьный предмет", VkKeyboardColor.PRIMARY),
         ("🎯 Кружок/секция", VkKeyboardColor.POSITIVE)],
        [("✅ Готово с днём", VkKeyboardColor.SECONDARY),
         ("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def subjects_for_grade_keyboard(grade, added=None):
    subjects = GRADE_SUBJECTS.get(grade, [])
    if added is None:
        added = set()
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for s in subjects[i:i+2]:
            mark = " ✅" if s in added else ""
            row.append((s + mark, VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)

def extra_keyboard():
    rows = []
    for i in range(0, len(EXTRA_ACTIVITIES), 2):
        row = []
        for a in EXTRA_ACTIVITIES[i:i+2]:
            row.append((a, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)

def time_keyboard():
    rows = []
    for i in range(0, len(TIMES), 3):
        row = []
        for t in TIMES[i:i+3]:
            row.append((t, VkKeyboardColor.SECONDARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)

def categories_keyboard():
    cats = list(SUBJECT_CATEGORIES.keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = []
        for c in cats[i:i+2]:
            row.append((f"📁 {c}", VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)

def subjects_keyboard(category):
    subjects = SUBJECT_CATEGORIES.get(category, [])
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for s in subjects[i:i+2]:
            row.append((s, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([
        ("⬅️ К категориям", VkKeyboardColor.SECONDARY),
        ("🏠 Главное меню", VkKeyboardColor.SECONDARY),
    ])
    return build_keyboard(rows)

def cok_subject_menu_keyboard(subject):
    return build_keyboard([
        [("🤖 Объяснить тему", VkKeyboardColor.POSITIVE)],
        [("📚 Ресурсы", VkKeyboardColor.PRIMARY)],
        [("⬅️ К предметам", VkKeyboardColor.SECONDARY),
         ("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def homework_keyboard():
    return build_keyboard([
        [("➕ Добавить ДЗ", VkKeyboardColor.PRIMARY),
         ("📋 Показать всё", VkKeyboardColor.SECONDARY)],
        [("✅ Отметить выполнено", VkKeyboardColor.POSITIVE),
         ("🗑 Удалить", VkKeyboardColor.NEGATIVE)],
        [("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def grades_keyboard():
    return build_keyboard([
        [("➕ Добавить оценку", VkKeyboardColor.PRIMARY),
         ("📊 Средний балл", VkKeyboardColor.POSITIVE)],
        [("📋 Все оценки", VkKeyboardColor.SECONDARY),
         ("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def reminders_keyboard():
    return build_keyboard([
        [("➕ Своё напоминание", VkKeyboardColor.POSITIVE)],
        [("📋 Что сегодня", VkKeyboardColor.PRIMARY),
         ("📋 Все напоминания", VkKeyboardColor.PRIMARY)],
        [("🗑 Удалить напоминание", VkKeyboardColor.NEGATIVE)],
        [("🔔 Включить", VkKeyboardColor.POSITIVE),
         ("🔕 Выключить", VkKeyboardColor.NEGATIVE)],
        [("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

def ai_keyboard():
    return build_keyboard([
        [("📝 Спросить ИИ-тьютора", VkKeyboardColor.POSITIVE)],
        [("📈 Мой прогресс", VkKeyboardColor.PRIMARY),
         ("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
    ])

# ═══════════════════════════════════════════
#  ОТПРАВКА СООБЩЕНИЙ
# ═══════════════════════════════════════════

def send_message(user_id, text, keyboard=None):
    vk.messages.send(
        user_id=user_id, message=text,
        keyboard=keyboard, random_id=random.randint(0, 2**31 - 1),
    )

def send_reminder(user_id, text):
    try:
        vk_rem.messages.send(
            user_id=user_id, message=text,
            random_id=random.randint(0, 2**31 - 1),
        )
    except Exception as e:
        print(f"Ошибка отправки напоминания: {e}")

# ═══════════════════════════════════════════
#  РАСПИСАНИЕ
# ═══════════════════════════════════════════

def get_today_key():
    return DAYS_ORDER[datetime.now().weekday()]

def format_day(day_key, items):
    name = DAYS_RU[day_key]
    if not items:
        return f"📅 {name}: нет занятий"
    sorted_items = sorted(items, key=lambda x: x.get("time", "99:99"))
    lines = [f"📅 {name}:"]
    for i, item in enumerate(sorted_items, 1):
        icon = "🎯" if item.get("type") == "extra" else "📖"
        lines.append(f"  {i}. {item['time']} {icon} {item['subject']}")
    return "\n".join(lines)

def format_week(week):
    parts = [format_day(d, week.get(d, [])) for d in DAYS_ORDER if week.get(d)]
    return "\n\n".join(parts) if parts else "Расписание пустое."

def _minus_15(t):
    try:
        h, m = map(int, t.split(":"))
        total = h * 60 + m - 15
        if total < 0:
            total = 0
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return t

def _minus_30(t):
    try:
        h, m = map(int, t.split(":"))
        total = h * 60 + m - 30
        if total < 0:
            total = 0
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return t

# ═══════════════════════════════════════════
#  СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════

user_state = {}

# ═══════════════════════════════════════════
#  ФОНОВЫЙ ПОТОК — НАПОМИНАНИЯ + РАССЫЛКИ
# ═══════════════════════════════════════════

def reminder_loop():
    while True:
        try:
            now = datetime.now()
            today_key = get_today_key()
            current_hm = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # ── 1. Напоминания из расписания (за 15 мин) ──
            for uid_str, sched in DATA.get("schedules", {}).items():
                if not DATA.get("reminders_on", {}).get(uid_str, True):
                    continue
                week = sched.get("week", {})
                today_items = week.get(today_key, [])
                uid = int(uid_str)
                if uid not in sent_reminders:
                    sent_reminders[uid] = set()
                for item in today_items:
                    t = item.get("time", "")
                    subj = item.get("subject", "")
                    try:
                        h, m = map(int, t.split(":"))
                        item_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        rem_dt = item_dt - timedelta(minutes=15)
                        rem_str = rem_dt.strftime("%H:%M")
                    except Exception:
                        continue
                    key = f"{today_str}_{t}_{subj}"
                    if current_hm == rem_str and key not in sent_reminders[uid]:
                        icon = "🎯" if item.get("type") == "extra" else "📖"
                        msg = (f"⏰ Напоминание!\n\nЧерез 15 минут:\n"
                               f"{icon} {subj} в {t}\n\n"
                               f"Проверь, всё ли готово! 🎒")
                        send_reminder(uid, msg)
                        sent_reminders[uid].add(key)

            # ── 2. Свои напоминания (за 30 и 15 минут) ──
            for uid_str, reminders in DATA.get("custom_reminders", {}).items():
                if not DATA.get("reminders_on", {}).get(uid_str, True):
                    continue
                uid = int(uid_str)
                changed = False
                for rem in reminders:
                    try:
                        rem_dt = datetime.fromisoformat(rem["datetime"])
                    except Exception:
                        continue
                    rem_30 = rem_dt - timedelta(minutes=30)
                    if now >= rem_30 and not rem.get("sent_30"):
                        msg = f"⏰ Напоминание (за 30 минут)!\n\n{rem['text']}"
                        send_reminder(uid, msg)
                        rem["sent_30"] = True
                        changed = True
                    rem_15 = rem_dt - timedelta(minutes=15)
                    if now >= rem_15 and not rem.get("sent_15"):
                        msg = f"⏰ Напоминание (за 15 минут)!\n\n{rem['text']}"
                        send_reminder(uid, msg)
                        rem["sent_15"] = True
                        changed = True
                    if now >= rem_dt and rem.get("sent_30") and rem.get("sent_15"):
                        rem["sent"] = True
                        changed = True
                if changed:
                    save_data()

            # ── 3. Утренняя мотивация (07:30) ──
            if current_hm == f"{MORNING_HOUR:02d}:{MORNING_MIN:02d}":
                sent_m = DATA.setdefault("sent_morning", {})
                for uid_str in DATA.get("schedules", {}):
                    if today_str not in sent_m.get(uid_str, ""):
                        quote = random.choice(MORNING_QUOTES)
                        tip = random.choice(STUDY_TIPS)
                        msg = f"{quote}\n\n{tip}"
                        try:
                            send_reminder(int(uid_str), msg)
                        except Exception:
                            pass
                        sent_m[uid_str] = today_str
                        save_data()

            # ── 4. Вечерний совет (21:00) ──
            if current_hm == f"{EVENING_HOUR:02d}:{EVENING_MIN:02d}":
                sent_e = DATA.setdefault("sent_evening", {})
                for uid_str in DATA.get("schedules", {}):
                    if today_str not in sent_e.get(uid_str, ""):
                        quote = random.choice(EVENING_QUOTES)
                        tip = random.choice(STUDY_TIPS)
                        msg = f"{quote}\n\n{tip}"
                        try:
                            send_reminder(int(uid_str), msg)
                        except Exception:
                            pass
                        sent_e[uid_str] = today_str
                        save_data()

        except Exception as e:
            print(f"Ошибка в reminder_loop: {e}")
        time.sleep(60)

# ═══════════════════════════════════════════
#  ОБРАБОТКА СООБЩЕНИЙ
# ═══════════════════════════════════════════

def handle_message(event):
    text = event.text
    uid = event.user_id
    uid_s = str(uid)

    global DATA
    DATA = load_data()

    # ── АКТИВНОЕ СОСТОЯНИЕ ──
    if uid in user_state:
        st = user_state[uid]
        step = st["step"]

        # ── Настройка расписания ──
        if step == "setup_grade":
            if text in GRADE_SUBJECTS:
                st["grade"] = text
                DATA.setdefault("schedules", {}).setdefault(
                    uid_s, {"grade": text, "week": {}})["grade"] = text
                save_data()
                st["step"] = "setup_day"
                send_message(uid, "Выбери день недели:", day_keyboard())
            else:
                send_message(uid, "Выбери класс кнопкой 👇", grade_keyboard())
            return

        if step == "setup_day":
            dk = DAY_NAME_TO_KEY.get(text.lower())
            if dk:
                st["day"] = dk
                st["step"] = "setup_type"
                send_message(uid, f"🗓 {DAYS_RU[dk]}\n\nЧто добавляем?",
                             sched_type_keyboard())
            elif text == "⬅️ Назад":
                del user_state[uid]
                send_message(uid, "Меню расписания:", schedule_menu_keyboard())
            else:
                send_message(uid, "Выбери день кнопкой 👇", day_keyboard())
            return

        if step == "setup_type":
            if text == "📖 Школьный предмет":
                grade = DATA["schedules"].get(uid_s, {}).get(
                    "grade", st.get("grade", "5 класс"))
                added = set()
                for item in DATA["schedules"].get(uid_s, {}).get(
                        "week", {}).get(st["day"], []):
                    if item.get("type") == "lesson":
                        added.add(item["subject"])
                st["step"] = "setup_subject"
                send_message(uid, "Выбери предмет:",
                             subjects_for_grade_keyboard(grade, added))
            elif text == "🎯 Кружок/секция":
                st["step"] = "setup_extra"
                send_message(uid, "Что за занятие?", extra_keyboard())
            elif text == "✅ Готово с днём":
                save_data()
                del user_state[uid]
                add_points(uid_s, 5, "настройка расписания")
                send_message(uid,
                    "✅ Расписание на этот день сохранено!\n"
                    "+5 баллов! 🎉\n\n"
                    "Хочешь настроить другой день?",
                    schedule_menu_keyboard())
            elif text == "🏠 Главное меню":
                save_data()
                del user_state[uid]
                send_message(uid, "Главное меню:", main_keyboard())
            else:
                send_message(uid, "Выбери кнопкой 👇", sched_type_keyboard())
            return

        if step == "setup_subject":
            if text == "⬅️ Назад":
                st["step"] = "setup_type"
                send_message(uid, "Что добавляем?", sched_type_keyboard())
                return
            grade = DATA["schedules"].get(uid_s, {}).get(
                "grade", st.get("grade", ""))
            if text in GRADE_SUBJECTS.get(grade, []):
                st["pending"] = {"subject": text, "type": "lesson"}
                st["step"] = "setup_time"
                send_message(uid, f"Во сколько начинается «{text}»?",
                             time_keyboard())
            else:
                send_message(uid, "Выбери предмет кнопкой 👇",
                             subjects_for_grade_keyboard(grade))
            return

        if step == "setup_extra":
            if text == "⬅️ Назад":
                st["step"] = "setup_type"
                send_message(uid, "Что добавляем?", sched_type_keyboard())
                return
            if text == "➕ Другое":
                st["step"] = "setup_custom"
                send_message(uid, "Напиши название занятия текстом:")
                return
            if text in EXTRA_ACTIVITIES:
                st["pending"] = {"subject": text, "type": "extra"}
                st["step"] = "setup_time"
                send_message(uid, f"Во сколько начинается «{text}»?",
                             time_keyboard())
            else:
                send_message(uid, "Выбери кнопкой 👇", extra_keyboard())
            return

        if step == "setup_custom":
            if text.strip():
                st["pending"] = {"subject": text.strip(), "type": "extra"}
                st["step"] = "setup_time"
                send_message(uid, f"Во сколько начинается «{text.strip()}»?",
                             time_keyboard())
            else:
                send_message(uid, "Напиши название занятия текстом:")
            return

        if step == "setup_time":
            if text == "⬅️ Назад":
                st["step"] = "setup_type"
                send_message(uid, "Что добавляем?", sched_type_keyboard())
                return
            if text in TIMES:
                day = st["day"]
                pending = st["pending"]
                entry = {"subject": pending["subject"], "time": text,
                         "type": pending["type"]}
                DATA["schedules"].setdefault(uid_s, {}).setdefault(
                    "week", {}).setdefault(day, []).append(entry)
                save_data()
                st["step"] = "setup_type"
                icon = "🎯" if pending["type"] == "extra" else "📖"
                send_message(uid,
                    f"✅ Добавлено: {icon} {pending['subject']} в {text}\n\n"
                    "Что ещё?", sched_type_keyboard())
            else:
                send_message(uid, "Выбери время кнопкой 👇", time_keyboard())
            return

        # ── ЦОК: меню предмета ──
        if step == "cok_subject_menu":
            subject = st.get("subject", "")
            if text == "🤖 Объяснить тему":
                st["step"] = "cok_topic_input"
                examples = TOPIC_EXAMPLES.get(subject, "напиши тему, которую хочешь понять")
                send_message(uid,
                    f"🤖 ИИ-тьютор — предмет: {subject}\n\n"
                    f"Напиши КОНКРЕТНУЮ тему, которую не понимаешь.\n\n"
                    f"Например для {subject}:\n{examples}")
                return
            if text == "📚 Ресурсы":
                resources = SUBJECT_RESOURCES.get(subject,
                    ["📚 ЦОК — библиотека цифрового контента"])
                lines = [f"📚 Ресурсы по предмету «{subject}»:\n"]
                for r in resources:
                    lines.append(f"  {r}")
                lines.append("\n💡 Изучи материал, а если что-то непонятно — "
                             "нажми «Объяснить тему»!")
                send_message(uid, "\n".join(lines),
                             cok_subject_menu_keyboard(subject))
                return
            if text == "⬅️ К предметам":
                cat = st.get("category", "")
                del user_state[uid]
                if cat:
                    send_message(uid, f"Предметы категории «{cat}»:",
                                 subjects_keyboard(cat))
                else:
                    send_message(uid, "Выбери категорию:", categories_keyboard())
                return
            if text == "🏠 Главное меню":
                del user_state[uid]
                send_message(uid, "Главное меню:", main_keyboard())
                return
            send_message(uid, "Выбери кнопкой 👇",
                         cok_subject_menu_keyboard(subject))
            return

        # ── ЦОК: ввод конкретной темы ──
        if step == "cok_topic_input":
            if text.strip() and len(text.strip()) > 2:
                topic = text.strip()
                subject = st.get("subject", "")
                grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade", "")
                track_topic(uid_s, topic, subject)
                del user_state[uid]
                send_message(uid,
                    f"🤖 ИИ-тьютор думает...\n"
                    f"Предмет: {subject} | Тема: {topic} ⏳",
                    ai_keyboard())
                explanation = ai_explain(topic, grade, subject)
                add_points(uid_s, 20, "вопрос ИИ")
                pts_info = points_info(uid_s)
                full_msg = (f"🤖 ИИ-тьютор | {subject}\n\n"
                            f"{explanation}\n\n"
                            f"---\n{pts_info} (+20 баллов! 🎉)")
                send_message(uid, full_msg, ai_keyboard())
            else:
                subject = st.get("subject", "")
                short = TOPIC_EXAMPLES_SHORT.get(subject, "напиши тему")
                send_message(uid,
                    f"Напиши конкретную тему по предмету «{subject}».\n"
                    f"Например: {short}")
            return

        # ── Своё напоминание: текст ──
        if step == "custom_rem_text":
            if text.strip() and len(text.strip()) > 2:
                st["rem_text"] = text.strip()
                st["step"] = "custom_rem_date"
                send_message(uid,
                    "Когда напомнить? Напиши дату и время.\n\n"
                    "Примеры:\n"
                    "• сегодня 18:00\n"
                    "• завтра 15:30\n"
                    "• послезавтра 9:00\n"
                    "• понедельник 18:00\n"
                    "• пт 16:00\n"
                    "• 15.09 18:00\n"
                    "• 18:00 (сегодня, если прошло — завтра)\n\n"
                    "Напомню два раза: за 30 и за 15 минут!")
            else:
                send_message(uid, "Напиши, о чём напомнить (минимум 3 символа):")
            return

        # ── Своё напоминание: дата ──
        if step == "custom_rem_date":
            if text == "⬅️ Назад" or text.lower() == "отмена":
                del user_state[uid]
                send_message(uid, "Создание напоминания отменено.",
                             reminders_keyboard())
                return
            dt = parse_reminder_datetime(text)
            if dt:
                entry = {
                    "text": st["rem_text"],
                    "datetime": dt.isoformat(),
                    "sent_30": False,
                    "sent_15": False,
                    "sent": False,
                }
                DATA.setdefault("custom_reminders", {}).setdefault(
                    uid_s, []).append(entry)
                save_data()
                del user_state[uid]
                add_points(uid_s, 10, "создал напоминание")
                send_message(uid,
                    f"✅ Напоминание создано!\n\n"
                    f"📝 {st['rem_text']}\n"
                    f"⏰ {format_dt(dt)}\n\n"
                    f"Напомню два раза: за 30 и за 15 минут.\n"
                    f"+10 баллов! 🎉",
                    reminders_keyboard())
            else:
                send_message(uid,
                    "Не понял дату/время 😕\n\n"
                    "Попробуй так:\n"
                    "• сегодня 18:00\n"
                    "• завтра 15:30\n"
                    "• понедельник 18:00\n"
                    "• 15.09 18:00")
            return

        # ── Своё напоминание: удаление ──
        if step == "custom_rem_del":
            try:
                num = int(text) - 1
                rems = DATA.get("custom_reminders", {}).get(uid_s, [])
                active = [r for r in rems if not r.get("sent")]
                if 0 <= num < len(active):
                    rem_to_del = active[num]
                    rems.remove(rem_to_del)
                    save_data()
                    del user_state[uid]
                    send_message(uid, f"🗑 Удалено: {rem_to_del['text']}",
                                 reminders_keyboard())
                    return
            except ValueError:
                pass
            send_message(uid, "Напиши номер цифрой:")
            return

        # ── ИИ-тьютор (из главного меню) ──
        if step == "ai_input":
            if text.strip() and len(text.strip()) > 2:
                topic = text.strip()
                grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade", "")
                track_topic(uid_s, topic)
                del user_state[uid]
                send_message(uid, "🤖 ИИ-тьютор думает... ⏳", ai_keyboard())
                explanation = ai_explain(topic, grade)
                add_points(uid_s, 20, "вопрос ИИ")
                pts_info = points_info(uid_s)
                full_msg = (f"🤖 ИИ-тьютор:\n\n{explanation}\n\n"
                            f"---\n{pts_info} (+20 баллов! 🎉)")
                send_message(uid, full_msg, ai_keyboard())
            else:
                send_message(uid,
                    "Напиши тему, которую хочешь понять. "
                    "Например: «дроби», «теорема Пифагора»")
            return

        # ── Домашка ──
        if step == "hw_input":
            if ":" in text:
                parts = text.split(":", 1)
                subj = parts[0].strip()
                desc = parts[1].strip()
                DATA["homework"].setdefault(uid_s, []).append(
                    {"subject": subj, "desc": desc, "done": False})
                save_data()
                del user_state[uid]
                add_points(uid_s, 10, "добавил ДЗ")
                send_message(uid, f"✅ ДЗ по «{subj}» добавлено! +10 баллов! 🎉",
                             homework_keyboard())
            else:
                send_message(uid,
                    "Формат: Предмет: что задали\n"
                    "Пример: Математика: стр. 45 № 3,4")
            return

        if step == "hw_done":
            hw_list = DATA.get("homework", {}).get(uid_s, [])
            try:
                num = int(text) - 1
                if 0 <= num < len(hw_list):
                    hw_list[num]["done"] = True
                    save_data()
                    del user_state[uid]
                    add_points(uid_s, 15, "выполнил ДЗ")
                    send_message(uid, "✅ Отлично! +15 баллов! 🎉",
                                 homework_keyboard())
                    return
            except ValueError:
                pass
            send_message(uid, "Напиши номер ДЗ цифрой:")
            return

        if step == "hw_del":
            hw_list = DATA.get("homework", {}).get(uid_s, [])
            try:
                num = int(text) - 1
                if 0 <= num < len(hw_list):
                    hw_list.pop(num)
                    save_data()
                    del user_state[uid]
                    send_message(uid, "🗑 Удалено!", homework_keyboard())
                    return
            except ValueError:
                pass
            send_message(uid, "Напиши номер цифрой:")
            return

        # ── Оценки ──
        if step == "grade_input":
            if ":" in text:
                parts = text.split(":", 1)
                subj = parts[0].strip()
                val = parts[1].strip()
                DATA["grades"].setdefault(uid_s, []).append(
                    {"subject": subj, "grade": val,
                     "date": datetime.now().strftime("%d.%m")})
                save_data()
                del user_state[uid]
                add_points(uid_s, 10, "добавил оценку")
                send_message(uid,
                    f"✅ Оценка {val} по «{subj}» добавлена! +10 баллов! 🎉",
                    grades_keyboard())
            else:
                send_message(uid,
                    "Формат: Предмет: оценка\nПример: Алгебра: 4")
            return

    # ═══════════════════════════════════════════
    #  ОСНОВНОЕ МЕНЮ
    # ═══════════════════════════════════════════

    text_lower = text.lower()

    if text_lower in ["начало", "начать", "привет", "меню",
                      "🏠 главное меню", "старт"]:
        send_message(uid,
            "Привет! Я «Навигатор Успеха» v3.4 🎯\n\n"
            "Что я умею:\n"
            "🤖 ИИ-тьютор — объясняет темы простыми словами\n"
            "📅 Расписание — настрой на неделю, я напомню\n"
            "⏰ Напоминания — авто + свои (за 30 и 15 минут!)\n"
            "📊 Анализ нагрузки и трекинг прогресса\n"
            "🎯 Геймификация — баллы и уровни\n\n"
            "Чем займёмся?",
            main_keyboard())
        return

    # ── Расписание ──
    if text == "📅 Расписание":
        send_message(uid, "Управление расписанием:", schedule_menu_keyboard())
        return

    if text == "⚙️ Настроить расписание":
        grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade")
        if grade:
            user_state[uid] = {"step": "setup_day"}
            send_message(uid, f"Твой класс: {grade}\nВыбери день недели:",
                         day_keyboard())
        else:
            user_state[uid] = {"step": "setup_grade"}
            send_message(uid, "Сначала выбери класс:", grade_keyboard())
        return

    if text == "📋 На сегодня":
        week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
        today = get_today_key()
        send_message(uid,
            format_day(today, week.get(today, [])) +
            "\n\n⚠️ Я напомню за 15 минут до начала каждого занятия!",
            schedule_menu_keyboard())
        return

    if text == "📋 На неделю":
        week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
        if week:
            send_message(uid, format_week(week), schedule_menu_keyboard())
        else:
            send_message(uid,
                "Расписание ещё не настроено. "
                "Нажми «Настроить расписание»!",
                schedule_menu_keyboard())
        return

    if text == "🗑 Очистить расписание":
        if uid_s in DATA.get("schedules", {}):
            DATA["schedules"][uid_s]["week"] = {}
            save_data()
        send_message(uid, "🗑 Расписание очищено.", schedule_menu_keyboard())
        return

    # ── Анализ недели ──
    if text == "📊 Анализ недели":
        send_message(uid, analyze_week(uid_s), main_keyboard())
        return

    # ── ИИ-тьютор ──
    if text == "🤖 ИИ-тьютор":
        send_message(uid,
            "🤖 Я могу объяснить тему простыми словами!\n\n"
            "Напиши, что не понимаешь. Например:\n"
            "• «дроби»\n"
            "• «теорема Пифагора»\n"
            "• «приставки ПРЕ и ПРИ»\n\n"
            "Я объясню на примерах и задам проверочный вопрос 🎯",
            ai_keyboard())
        return

    if text == "📝 Спросить ИИ-тьютора":
        user_state[uid] = {"step": "ai_input"}
        send_message(uid, "Напиши тему, которую хочешь понять 👇")
        return

    # ── Трекинг прогресса ──
    if text == "📈 Мой прогресс":
        send_message(uid, progress_report(uid_s), ai_keyboard())
        return

    # ── Геймификация ──
    if text == "🎯 Мой уровень":
        send_message(uid, points_info(uid_s), main_keyboard())
        return

    # ── Напоминания ──
    if text == "⏰ Напоминания":
        enabled = DATA.get("reminders_on", {}).get(uid_s, True)
        status = "включены ✅" if enabled else "выключены ❌"
        send_message(uid,
            f"⏰ Напоминания {status}.\n\n"
            "Я напоминаю:\n"
            "• за 15 минут до урока/кружка/секции (из расписания)\n"
            "• за 30 и 15 минут — для твоих собственных напоминаний\n\n"
            "Нажми «Своё напоминание», чтобы создать новое!",
            reminders_keyboard())
        return

    if text == "➕ Своё напоминание":
        user_state[uid] = {"step": "custom_rem_text"}
        send_message(uid,
            "Напиши, о чём напомнить.\n\n"
            "Например: «Позвонить бабушке», «Собрать рюкзак», "
            "«Купить тетрадь»\n\n"
            "Напомню два раза: за 30 и за 15 минут до времени!")
        return

    if text == "📋 Что сегодня":
        week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
        today = get_today_key()
        lines = []
        sched_items = week.get(today, [])
        if sched_items:
            sorted_items = sorted(sched_items,
                                  key=lambda x: x.get("time", "99:99"))
            lines.append("📖 Из расписания:")
            for item in sorted_items:
                icon = "🎯" if item.get("type") == "extra" else "📖"
                lines.append(
                    f"  {item['time']} {icon} {item['subject']} "
                    f"→ напомню в {_minus_15(item['time'])}")
        rems = DATA.get("custom_reminders", {}).get(uid_s, [])
        today_rems = []
        for r in rems:
            if r.get("sent"):
                continue
            try:
                dt = datetime.fromisoformat(r["datetime"])
                if dt.date() == datetime.now().date():
                    today_rems.append(r)
            except Exception:
                continue
        if today_rems:
            lines.append("\n⏰ Мои напоминания:")
            for r in today_rems:
                try:
                    dt = datetime.fromisoformat(r["datetime"])
                    t_str = dt.strftime("%H:%M")
                    lines.append(
                        f"  {t_str} ⏰ {r['text']} "
                        f"(напомню в {_minus_30(t_str)} и {_minus_15(t_str)})")
                except Exception:
                    lines.append(f"  ⏰ {r['text']}")
        if not lines:
            send_message(uid, "На сегодня нет напоминаний! 😎",
                         reminders_keyboard())
        else:
            send_message(uid, "\n".join(lines), reminders_keyboard())
        return

    if text == "📋 Все напоминания":
        rems = DATA.get("custom_reminders", {}).get(uid_s, [])
        active = [r for r in rems if not r.get("sent")]
        if not active:
            send_message(uid, "У тебя нет активных напоминаний.",
                         reminders_keyboard())
        else:
            lines = ["📋 Все напоминания:"]
            for i, r in enumerate(active, 1):
                try:
                    dt = datetime.fromisoformat(r["datetime"])
                    lines.append(f"{i}. {format_dt(dt)} — {r['text']}")
                except Exception:
                    lines.append(f"{i}. {r['text']}")
            send_message(uid, "\n".join(lines), reminders_keyboard())
        return

    if text == "🗑 Удалить напоминание":
        rems = DATA.get("custom_reminders", {}).get(uid_s, [])
        active = [r for r in rems if not r.get("sent")]
        if not active:
            send_message(uid, "Удалять нечего — нет активных напоминаний.",
                         reminders_keyboard())
        else:
            user_state[uid] = {"step": "custom_rem_del"}
            lines = ["Напиши номер для удаления:"]
            for i, r in enumerate(active, 1):
                try:
                    dt = datetime.fromisoformat(r["datetime"])
                    lines.append(f"{i}. {format_dt(dt)} — {r['text']}")
                except Exception:
                    lines.append(f"{i}. {r['text']}")
            send_message(uid, "\n".join(lines))
        return

    if text == "🔔 Включить":
        DATA.setdefault("reminders_on", {})[uid_s] = True
        save_data()
        send_message(uid, "🔔 Напоминания включены!", reminders_keyboard())
        return

    if text == "🔕 Выключить":
        DATA.setdefault("reminders_on", {})[uid_s] = False
        save_data()
        send_message(uid, "🔕 Напоминания выключены.", reminders_keyboard())
        return

    # ── Домашка ──
    if text == "📝 Домашка":
        send_message(uid, "Управление домашними заданиями:",
                     homework_keyboard())
        return

    if text == "➕ Добавить ДЗ":
        user_state[uid] = {"step": "hw_input"}
        send_message(uid,
            "Напиши в формате:\nПредмет: что задали\n\n"
            "Пример: Математика: стр. 45 № 3,4")
        return

    if text == "📋 Показать всё":
        hw_list = DATA.get("homework", {}).get(uid_s, [])
        if not hw_list:
            send_message(uid, "Домашки нет! Можно отдохнуть 😎",
                         homework_keyboard())
        else:
            lines = ["📋 Твоя домашка:"]
            for i, hw in enumerate(hw_list, 1):
                mark = "✅" if hw.get("done") else "⬜"
                lines.append(f"{i}. {mark} {hw['subject']}: {hw['desc']}")
            send_message(uid, "\n".join(lines), homework_keyboard())
        return

    if text == "✅ Отметить выполнено":
        hw_list = DATA.get("homework", {}).get(uid_s, [])
        if not hw_list:
            send_message(uid, "Домашки нет!", homework_keyboard())
            return
        user_state[uid] = {"step": "hw_done"}
        lines = ["Напиши номер выполненного ДЗ:"]
        for i, hw in enumerate(hw_list, 1):
            if not hw.get("done"):
                lines.append(f"{i}. {hw['subject']}: {hw['desc']}")
        send_message(uid, "\n".join(lines))
        return

    if text == "🗑 Удалить":
        hw_list = DATA.get("homework", {}).get(uid_s, [])
        if not hw_list:
            send_message(uid, "Домашки нет!", homework_keyboard())
            return
        user_state[uid] = {"step": "hw_del"}
        lines = ["Напиши номер для удаления:"]
        for i, hw in enumerate(hw_list, 1):
            lines.append(f"{i}. {hw['subject']}: {hw['desc']}")
        send_message(uid, "\n".join(lines))
        return

    # ── Оценки ──
    if text == "🏆 Оценки":
        send_message(uid, "Управление оценками:", grades_keyboard())
        return

    if text == "➕ Добавить оценку":
        user_state[uid] = {"step": "grade_input"}
        send_message(uid,
            "Напиши в формате:\nПредмет: оценка\n\nПример: Алгебра: 4")
        return

    if text == "📊 Средний балл":
        gr_list = DATA.get("grades", {}).get(uid_s, [])
        if not gr_list:
            send_message(uid, "Оценок пока нет.", grades_keyboard())
            return
        by_subj = {}
        for g in gr_list:
            by_subj.setdefault(g["subject"], []).append(g["grade"])
        lines = ["📊 Средний балл по предметам:"]
        total_nums = []
        for subj, grades in by_subj.items():
            nums = []
            for gr in grades:
                try:
                    nums.append(float(gr.replace(",", ".")))
                except ValueError:
                    pass
            if nums:
                avg = sum(nums) / len(nums)
                total_nums.extend(nums)
                lines.append(f"  {subj}: {avg:.2f}")
        if total_nums:
            lines.append(
                f"\n📈 Общий средний: "
                f"{sum(total_nums) / len(total_nums):.2f}")
        send_message(uid, "\n".join(lines), grades_keyboard())
        return

    if text == "📋 Все оценки":
        gr_list = DATA.get("grades", {}).get(uid_s, [])
        if not gr_list:
            send_message(uid, "Оценок пока нет.", grades_keyboard())
        else:
            lines = ["📋 Все оценки:"]
            for i, g in enumerate(gr_list, 1):
                lines.append(f"{i}. {g['date']} — {g['subject']}: {g['grade']}")
            send_message(uid, "\n".join(lines), grades_keyboard())
        return

    # ── ЦОК ──
    if text == "📚 Учёба (ЦОК)":
        send_message(uid, "Выбери категорию предметов:", categories_keyboard())
        return

    for cat in SUBJECT_CATEGORIES:
        if text == f"📁 {cat}":
            send_message(uid, f"Предметы категории «{cat}»:",
                         subjects_keyboard(cat))
            return

    if text == "⬅️ К категориям":
        send_message(uid, "Выбери категорию:", categories_keyboard())
        return

    # Клик по предмету в ЦОК → меню предмета
    if text in ALL_SUBJECTS:
        cat_found = None
        for cat, subs in SUBJECT_CATEGORIES.items():
            if text in subs:
                cat_found = cat
                break
        user_state[uid] = {"step": "cok_subject_menu",
                          "subject": text, "category": cat_found}
        send_message(uid,
            f"📚 Предмет: {text}\n\nЧто хочешь сделать?",
            cok_subject_menu_keyboard(text))
        return

    # ── Помощь ──
    if text == "ℹ️ Помощь":
        send_message(uid,
            "🤖 Навигатор Успеха v3.4\n\n"
            "Что я умею:\n"
            "🤖 ИИ-тьютор — объясняю конкретные темы простыми словами\n"
            "📅 Расписание — настрой на неделю, я напомню\n"
            "⏰ Напоминания — авто (15 мин) + свои (30 и 15 мин)\n"
            "📝 Домашка — список заданий, отметка о выполнении\n"
            "🏆 Оценки — журнал и средний балл\n"
            "📊 Анализ недели — где перегрузка, как планировать\n"
            "📈 Мой прогресс — карта запросов к ИИ\n"
            "🎯 Мой уровень — баллы за активность\n"
            "📚 Учёба (ЦОК) — выбери предмет → ресурсы или "
            "объяснение темы\n\n"
            "🌅 Утром (07:30) — мотивация на день\n"
            "🌙 Вечером (21:00) — совет и напутствие\n\n"
            "ЦОК: выбери предмет, нажми «Объяснить тему» и напиши "
            "конкретную тему (например, «дроби» по математике).",
            main_keyboard())
        return

    if text == "⬅️ Назад":
        send_message(uid, "Главное меню:", main_keyboard())
        return

    # ── Не распознано → ИИ (если похоже на запрос темы) ──
    if text_lower.startswith("объясни") or text_lower.startswith("не понял") \
       or text_lower.startswith("не понимаю"):
        topic = text
        for prefix in ["объясни ", "не понял ", "не понимаю ",
                       "объясни", "не понял", "не понимаю"]:
            if topic.lower().startswith(prefix):
                topic = topic[len(prefix):].strip()
                break
        if topic and len(topic) > 2:
            grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade", "")
            track_topic(uid_s, topic)
            send_message(uid, "🤖 ИИ-тьютор думает... ⏳", ai_keyboard())
            explanation = ai_explain(topic, grade)
            add_points(uid_s, 20, "вопрос ИИ")
            pts_info = points_info(uid_s)
            full_msg = (f"🤖 ИИ-тьютор:\n\n{explanation}\n\n"
                        f"---\n{pts_info} (+20 баллов! 🎉)")
            send_message(uid, full_msg, ai_keyboard())
            return

    send_message(uid, "Нажми на кнопку в меню — я всё покажу! 👇",
                 main_keyboard())


# ═══════════════════════════════════════════
#  ЗАПУСК БОТА
# ═══════════════════════════════════════════

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
vk_rem_session = vk_api.VkApi(token=TOKEN)
vk_rem = vk_rem_session.get_api()

longpoll = VkLongPoll(vk_session)

# Запускаем фоновый поток
threading.Thread(target=reminder_loop, daemon=True).start()

print("=" * 50)
print("  Навигатор Успеха v3.4")
print("  ИИ-тьютор + ЦОК + авто-мотивация")
print("  Бот запущен! ✅")
print("=" * 50)

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        handle_message(event)
