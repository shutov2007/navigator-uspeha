#!/usr/bin/env python3
"""
Навигатор Успеха v3.0
Чат-бот для школьников (5-9 класс)
Конкурс «Технологии Первых» 2026

Возможности:
- ИИ-тьютор (GigaChat) — объясняет темы простыми словами
- Умный анализ нагрузки на неделю
- Трекинг прогресса и «карта пробелов»
- Геймификация: баллы и уровни
- Расписание с напоминаниями
- Домашние задания
- Оценки и средний балл
- Навигация по образовательным ресурсам (ЦОК)
"""

import json
import os
import random
import threading
import time
from datetime import datetime, timedelta

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# ═══════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════

TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "VK_TOKEN не найден! Добавь переменную окружения VK_TOKEN в панели Bothost."
    )

GIGA_KEY = os.getenv("GIGA_KEY", "")
DATA_FILE = "navigator_data.json"

# ═══════════════════════════════════════════════════════
#  ДАННЫЕ
# ═══════════════════════════════════════════════════════

GRADE_SUBJECTS = {
    "5 класс": ["Математика", "Русский язык", "Литература", "Английский язык",
                "История", "Биология", "География", "Обществознание",
                "Информатика", "Музыка", "ИЗО", "Технология", "Физкультура", "ОБЖ"],
    "6 класс": ["Математика", "Русский язык", "Литература", "Английский язык",
                "История", "Биология", "География", "Обществознание",
                "Информатика", "Музыка", "ИЗО", "Технология", "Физкультура", "ОБЖ"],
    "7 класс": ["Алгебра", "Геометрия", "Русский язык", "Литература",
                "Английский язык", "История", "Обществознание", "Биология",
                "География", "Физика", "Информатика", "Музыка", "ИЗО",
                "Технология", "Физкультура", "ОБЖ"],
    "8 класс": ["Алгебра", "Геометрия", "Русский язык", "Литература",
                "Английский язык", "История", "Обществознание", "Биология",
                "География", "Физика", "Химия", "Информатика",
                "ИЗО", "Технология", "Физкультура", "ОБЖ"],
    "9 класс": ["Алгебра", "Геометрия", "Русский язык", "Литература",
                "Английский язык", "История", "Обществознание", "Биология",
                "География", "Физика", "Химия", "Информатика", "Физкультура", "ОБЖ"],
}

EXTRA_ACTIVITIES = [
    "🎵 Музыкальная школа", "⚽ Спортивная секция", "📚 Репетитор",
    "🎭 Репетиция", "💃 Танцы", "🎨 Изостудия", "♟️ Шахматы", "➕ Другое",
]

DAYS_RU = {
    "monday": "Понедельник", "tuesday": "Вторник", "wednesday": "Среда",
    "thursday": "Четверг", "friday": "Пятница", "saturday": "Суббота",
    "sunday": "Воскресенье",
}
DAYS_ORDER = ["monday", "tuesday", "wednesday", "thursday",
               "friday", "saturday", "sunday"]
DAY_NAME_TO_KEY = {v.lower(): k for k, v in DAYS_RU.items()}

TIMES = ["08:30", "09:20", "10:10", "11:00", "12:00", "12:50",
         "13:40", "14:30", "15:20", "16:00", "17:00", "18:00", "19:00"]

SUBJECT_CATEGORIES = {
    "Основные": ["Математика", "Алгебра", "Геометрия",
                 "Русский язык", "Литература", "Английский язык"],
    "Естественные": ["Физика", "Химия", "Биология",
                     "География", "Информатика"],
    "Гуманитарные": ["История", "Обществознание",
                     "Окружающий мир", "Литературное чтение"],
    "Творчество и спорт": ["ИЗО", "Музыка", "Технология",
                           "Физкультура", "ОБЖ"],
}

SUBJECT_DIFFICULTY = {
    "Математика": 3, "Алгебра": 3, "Геометрия": 3,
    "Физика": 3, "Химия": 3,
    "Русский язык": 2, "Литература": 2, "Английский язык": 2,
    "История": 2, "Обществознание": 2, "Биология": 2, "Информатика": 2,
    "География": 1, "Музыка": 1, "ИЗО": 1,
    "Технология": 1, "Физкультура": 1, "ОБЖ": 1,
    "Окружающий мир": 1, "Литературное чтение": 1,
}

MORNING_QUOTES = [
    "Дорогу осилит идущий! Удачного дня! 🌅",
    "Сегодня отличный день, чтобы узнать что-то новое! 📖",
    "Маленькие шаги ведут к большим целям. Дерзай! 🎯",
    "Ты умнее, чем думаешь. Верь в себя! 💪",
    "Знания — это суперсила. Используй её сегодня! ⚡",
]

STUDY_TIPS = [
    "💡 Совет: читай учебник с карандашом — отмечай главное прямо в тексте.",
    "💡 Совет: объясни новую тему кому-то — так ты поймёшь её лучше.",
    "💡 Совет: 25 минут работы, 5 отдыха — техника Pomodoro. Попробуй!",
    "💡 Совет: повторяй материал перед сном — мозг запоминает лучше.",
]

LEVELS = [
    (0,    "🌱 Новичок"),
    (50,   "📚 Ученик"),
    (150,  "🎓 Знаток"),
    (300,  "🏆 Навигатор знаний"),
    (500,  "⭐ Магистр знаний"),
]

COK_RESOURCES = {
    "Математика": [
        "📌 Фоксфорд.Учебник — теория и задачи:\nhttps://foxford.ru/wiki/maths",
        "📌 Билимленд — интерактивные уроки:\nhttps://bilimland.kz/ru/subject/math",
    ],
    "Алгебра": [
        "📌 Фоксфорд.Учебник — алгебра:\nhttps://foxford.ru/wiki/maths",
        "📌 Math100.ru — задачи с решениями:\nhttps://math100.ru",
    ],
    "Геометрия": [
        "📌 Геометрия — анимированные доказательства:\nhttps://foxford.ru/wiki/maths/geometry",
        "📌 Math100.ru — задачи с решениями:\nhttps://math100.ru",
    ],
    "Русский язык": [
        "📌 Грамота.ру — справочник по русскому языку:\nhttps://gramota.ru",
        "📌 Фоксфорд.Учебник — русский язык:\nhttps://foxford.ru/wiki/russian",
    ],
    "Литература": [
        "📌 Литрес — школьная библиотека:\nhttps://www.litres.ru/shkolnaya-biblioteka/",
        "📌 Фоксфорд.Учебник — литература:\nhttps://foxford.ru/wiki/literature",
    ],
    "Английский язык": [
        "📌 Duolingo — бесплатная практика:\nhttps://www.duolingo.com",
        "📌 Lingualeo — курсы и словарь:\nhttps://lingualeo.com",
    ],
    "Физика": [
        "📌 Фоксфорд.Учебник — физика:\nhttps://foxford.ru/wiki/physics",
        "📌 Лекториум — курсы по физике:\nhttps://lektorium.tv",
    ],
    "Химия": [
        "📌 Фоксфорд.Учебник — химия:\nhttps://foxford.ru/wiki/chemistry",
        "📌 ХиМуза — викторины и опыты:\nhttps://himucha.ru",
    ],
    "Биология": [
        "📌 Фоксфорд.Учебник — биология:\nhttps://foxford.ru/wiki/biology",
        "📌 Лекториум — курсы по биологии:\nhttps://lektorium.tv",
    ],
    "География": [
        "📌 Фоксфорд.Учебник — география:\nhttps://foxford.ru/wiki/geography",
        "📌 Яндекс.Учебник — материалы по географии:\nhttps://education.yandex.ru",
    ],
    "История": [
        "📌 Arzamas — лекции по истории:\nhttps://arzamas.academy",
        "📌 Фоксфорд.Учебник — история:\nhttps://foxford.ru/wiki/history",
    ],
    "Обществознание": [
        "📌 Фоксфорд.Учебник — обществознание:\nhttps://foxford.ru/wiki/social-science",
    ],
    "Информатика": [
        "📌 Stepik — бесплатные курсы:\nhttps://stepik.org",
        "📌 Codecademy — основы программирования:\nhttps://www.codecademy.com",
    ],
    "Окружающий мир": [
        "📌 Яндекс.Учебник — окружающий мир:\nhttps://education.yandex.ru",
    ],
    "Литературное чтение": [
        "📌 Литрес — школьная библиотека:\nhttps://www.litres.ru/shkolnaya-biblioteka/",
    ],
    "Музыка": [
        "📌 Материалы для уроков музыки:\nhttps://music.uvic.me",
    ],
    "ИЗО": [
        "📌 Drawspace — бесплатные уроки рисования:\nhttps://drawspace.com",
    ],
    "Технология": [
        "📌 Stepik — курсы по технологии:\nhttps://stepik.org",
    ],
    "Физкультура": [
        "📌 Комплексы упражнений для дома (видео):\nhttps://ya.ru/video/search?text=утренняя+зарядка+для+школьников",
    ],
    "ОБЖ": [
        "📌 Фоксфорд.Учебник — ОБЖ:\nhttps://foxford.ru/wiki/obzh",
    ],
}

ALL_COK_SUBJECTS = set()
for _subs in SUBJECT_CATEGORIES.values():
    ALL_COK_SUBJECTS.update(_subs)

# ═══════════════════════════════════════════════════════
#  ХРАНИЛИЩЕ
# ═══════════════════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "schedules": {},
        "reminders_on": {},
        "homework": {},
        "grades": {},
        "points": {},
        "ai_history": {},
    }


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)


DATA = load_data()
user_state = {}
sent_reminders = {}

# ═══════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════

def get_today_key():
    return DAYS_ORDER[datetime.now().weekday()]


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


def add_points(uid_s, amount):
    points = DATA.get("points", {}).get(uid_s, 0) + amount
    DATA.setdefault("points", {})[uid_s] = points
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


def track_topic(uid_s, topic):
    DATA.setdefault("ai_history", {}).setdefault(uid_s, []).append({
        "topic": topic,
        "date": datetime.now().strftime("%d.%m"),
    })
    save_data()


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


def cok_resources(subject):
    items = COK_RESOURCES.get(subject, ["📌 Полезные ресурсы скоро появятся!"])
    return f"📚 Полезные ресурсы по предмету «{subject}»:\n\n" + \
           "\n\n".join(items) + \
           "\n\n⚠️ Некоторые ссылки могут открываться только из браузера."

# ═══════════════════════════════════════════════════════
#  ИИ-ТЬЮТОР (GigaChat)
# ═══════════════════════════════════════════════════════

def ai_explain(topic, grade=""):
    if not GIGA_KEY:
        return ("🤖 ИИ-тьютор пока не подключён. "
                "Чтобы его включить, нужно получить бесплатный ключ GigaChat "
                "на developers.sber.ru и добавить его в переменную GIGA_KEY.")
    try:
        from gigachat import GigaChat

        grade_hint = f"Ученик учится в {grade}." if grade else "Ученик 5-9 класса."

        system_prompt = (
            f"Ты — дружелюбный школьный тьютор. {grade_hint} "
            "Объясни тему ПРОСТЫМИ словами, с примерами из жизни. "
            "НЕ давай готовые ответы на домашние задания — подводи к пониманию. "
            "В конце задай ОДИН проверочный вопрос по теме. "
            "Ответ должен быть коротким — не больше 150 слов."
        )

        with GigaChat(credentials=GIGA_KEY, verify_ssl_certs=False) as giga:
            response = giga.chat({
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Объясни тему: {topic}"},
                ],
            })
            return response.choices[0].message.content
    except ImportError:
        return "🤖 Библиотека gigachat не установлена. Напиши: pip install gigachat"
    except Exception as e:
        return f"🤖 ИИ-тьютор временно недоступен. Попробуй позже! ({str(e)[:50]})"

# ═══════════════════════════════════════════════════════
#  АНАЛИЗ НАГРУЗКИ
# ═══════════════════════════════════════════════════════

def analyze_week(uid_s):
    week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
    if not week:
        return "Расписание не настроено. Сначала добавь уроки!"

    day_scores = {}
    for day_key in DAYS_ORDER:
        items = week.get(day_key, [])
        lessons = [i for i in items if i.get("type") == "lesson"]
        extras = [i for i in items if i.get("type") == "extra"]
        score = sum(SUBJECT_DIFFICULTY.get(i.get("subject", ""), 2) for i in lessons)
        day_scores[day_key] = {
            "lessons": len(lessons),
            "difficulty": score,
            "extras": len(extras),
        }

    hardest = max(day_scores.items(), key=lambda x: x[1]["difficulty"])
    easiest = min(day_scores.items(), key=lambda x: x[1]["difficulty"])

    lines = ["📊 Анализ недели:\n"]

    for day_key in DAYS_ORDER:
        info = day_scores[day_key]
        bar = "█" * min(info["difficulty"], 10)
        extra_str = f", +{info['extras']} кружков" if info["extras"] else ""
        lines.append(f"  {DAYS_RU[day_key]}: {bar} ({info['lessons']} уроков{extra_str})")

    lines.append("")
    if hardest[1]["difficulty"] >= 8:
        lines.append(f"⚠️ Самый тяжёлый день — {DAYS_RU[hardest[0]]}.")
        lines.append("💡 Совет: готовься к нему заранее.")
        if easiest[1]["difficulty"] <= 3 and easiest[0] != hardest[0]:
            lines.append(f"  В {DAYS_RU[easiest[0]]} меньше нагрузки — займись подготовкой.")
    else:
        lines.append("✅ Нагрузка распределена равномерно. Так держать!")

    return "\n".join(lines)

# ═══════════════════════════════════════════════════════
#  ТРЕКИНГ ПРОГРЕССА
# ═══════════════════════════════════════════════════════

def progress_report(uid_s):
    history = DATA.get("ai_history", {}).get(uid_s, [])
    if not history:
        return ("Ты ещё не спрашивал у ИИ-тьютора. "
                "Напиши «Объясни тему: ...», и я начну отслеживать!")

    topic_count = {}
    for entry in history:
        t = entry["topic"].lower()
        topic_count[t] = topic_count.get(t, 0) + 1

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

# ═══════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════

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
         ("⭐ Мотивация", VkKeyboardColor.SECONDARY)],
        [("💡 Совет дня", VkKeyboardColor.SECONDARY),
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
        for s in subjects[i:i + 2]:
            mark = " ✅" if s in added else ""
            row.append((s + mark, VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def extra_keyboard():
    rows = []
    for i in range(0, len(EXTRA_ACTIVITIES), 2):
        row = []
        for a in EXTRA_ACTIVITIES[i:i + 2]:
            row.append((a, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def time_keyboard():
    rows = []
    for i in range(0, len(TIMES), 3):
        row = []
        for t in TIMES[i:i + 3]:
            row.append((t, VkKeyboardColor.SECONDARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def categories_keyboard():
    cats = list(SUBJECT_CATEGORIES.keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = []
        for c in cats[i:i + 2]:
            row.append((f"📁 {c}", VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("🏠 Главное меню", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def subjects_keyboard(category):
    subjects = SUBJECT_CATEGORIES.get(category, [])
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for s in subjects[i:i + 2]:
            row.append((s, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([
        ("⬅️ К категориям", VkKeyboardColor.SECONDARY),
        ("🏠 Главное меню", VkKeyboardColor.SECONDARY),
    ])
    return build_keyboard(rows)


def cok_subject_keyboard():
    return build_keyboard([
        [("🤖 Объяснить тему", VkKeyboardColor.POSITIVE)],
        [("📚 Полезные ресурсы", VkKeyboardColor.PRIMARY)],
        [("⬅️ К категориям", VkKeyboardColor.SECONDARY),
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
        [("📋 Мои напоминания сегодня", VkKeyboardColor.PRIMARY)],
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

# ═══════════════════════════════════════════════════════
#  ОТПРАВКА СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════

def send_message(user_id, text, keyboard=None):
    vk.messages.send(
        user_id=user_id,
        message=text,
        keyboard=keyboard,
        random_id=random.randint(0, 2 ** 31 - 1),
    )


def send_reminder(user_id, text):
    try:
        vk_rem.messages.send(
            user_id=user_id,
            message=text,
            random_id=random.randint(0, 2 ** 31 - 1),
        )
    except Exception as e:
        print(f"Ошибка отправки напоминания: {e}")

# ═══════════════════════════════════════════════════════
#  ФОНОВЫЙ ПОТОК — НАПОМИНАНИЯ
# ═══════════════════════════════════════════════════════

def reminder_loop():
    while True:
        try:
            now = datetime.now()
            today_key = get_today_key()
            current_hm = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

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
                        msg = (f"⏰ Напоминание!\n\n"
                               f"Через 15 минут:\n{icon} {subj} в {t}\n\n"
                               f"Проверь, всё ли готово! 🎒")
                        send_reminder(uid, msg)
                        sent_reminders[uid].add(key)
        except Exception as e:
            print(f"Ошибка в reminder_loop: {e}")
        time.sleep(60)

# ═══════════════════════════════════════════════════════
#  ОБРАБОТКА СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════

def handle_message(event):
    global DATA

    text = event.text
    uid = event.user_id
    uid_s = str(uid)

    DATA = load_data()

    # ── АКТИВНОЕ СОСТОЯНИЕ ──
    if uid in user_state:
        st = user_state[uid]
        step = st["step"]

        # ── Настройка расписания: выбор класса ──
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

        # ── Настройка расписания: выбор дня ──
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

        # ── Настройка расписания: тип занятия ──
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
                add_points(uid_s, 5)
                send_message(uid,
                    "✅ Расписание на этот день сохранено!\n+5 баллов! 🎉\n\n"
                    "Хочешь настроить другой день?",
                    schedule_menu_keyboard())
            elif text == "🏠 Главное меню":
                save_data()
                del user_state[uid]
                send_message(uid, "Главное меню:", main_keyboard())
            else:
                send_message(uid, "Выбери кнопкой 👇", sched_type_keyboard())
            return

        # ── Настройка расписания: выбор предмета ──
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

        # ── Настройка расписания: выбор кружка ──
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

        # ── Настройка расписания: своё название ──
        if step == "setup_custom":
            if text.strip():
                st["pending"] = {"subject": text.strip(), "type": "extra"}
                st["step"] = "setup_time"
                send_message(uid, f"Во сколько начинается «{text.strip()}»?",
                             time_keyboard())
            else:
                send_message(uid, "Напиши название занятия текстом:")
            return

        # ── Настройка расписания: выбор времени ──
        if step == "setup_time":
            if text == "⬅️ Назад":
                st["step"] = "setup_type"
                send_message(uid, "Что добавляем?", sched_type_keyboard())
                return
            if text in TIMES:
                day = st["day"]
                pending = st["pending"]
                entry = {"subject": pending["subject"],
                         "time": text,
                         "type": pending["type"]}
                DATA["schedules"].setdefault(uid_s, {}).setdefault(
                    "week", {}).setdefault(day, []).append(entry)
                save_data()
                st["step"] = "setup_type"
                icon = "🎯" if pending["type"] == "extra" else "📖"
                send_message(uid,
                    f"✅ Добавлено: {icon} {pending['subject']} в {text}\n\nЧто ещё?",
                    sched_type_keyboard())
            else:
                send_message(uid, "Выбери время кнопкой 👇", time_keyboard())
            return

        # ── ИИ-тьютор: ввод темы ──
        if step == "ai_input":
            if text.strip() and len(text.strip()) > 2:
                topic = text.strip()
                grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade", "")
                track_topic(uid_s, topic)
                del user_state[uid]
                send_message(uid, "🤖 ИИ-тьютор думает... ⏳", ai_keyboard())
                explanation = ai_explain(topic, grade)
                add_points(uid_s, 20)
                pts = points_info(uid_s)
                send_message(uid,
                    f"🤖 ИИ-тьютор:\n\n{explanation}\n\n---\n{pts} (+20 баллов! 🎉)",
                    ai_keyboard())
            else:
                send_message(uid,
                    "Напиши тему, которую хочешь понять. "
                    "Например: «дроби», «теорема Пифагора», «приставки ПРЕ и ПРИ»")
            return

        # ── ЦОК: выбран предмет — ожидание действия ──
        if step == "cok_subject":
            if text == "🤖 Объяснить тему":
                subj = st["subject"]
                del user_state[uid]
                grade = DATA.get("schedules", {}).get(uid_s, {}).get("grade", "")
                track_topic(uid_s, subj)
                send_message(uid, f"🤖 ИИ-тьютор объясняет: {subj}... ⏳",
                             ai_keyboard())
                explanation = ai_explain(
                    f"Расскажи кратко, что изучает предмет «{subj}» "
                    f"и какие главные темы в нём", grade)
                add_points(uid_s, 20)
                pts = points_info(uid_s)
                send_message(uid,
                    f"🤖 ИИ-тьютор:\n\n{explanation}\n\n---\n{pts} (+20 баллов! 🎉)",
                    ai_keyboard())
                return

            if text == "📚 Полезные ресурсы":
                subj = st["subject"]
                del user_state[uid]
                send_message(uid, cok_resources(subj),
                    build_keyboard([
                        [("⬅️ К категориям", VkKeyboardColor.SECONDARY),
                         ("🏠 Главное меню", VkKeyboardColor.SECONDARY)],
                    ]))
                return

            if text == "⬅️ К категориям":
                del user_state[uid]
                send_message(uid, "Выбери категорию:", categories_keyboard())
                return

            if text == "🏠 Главное меню":
                del user_state[uid]
                send_message(uid, "Главное меню:", main_keyboard())
                return

            send_message(uid, "Выбери кнопкой 👇", cok_subject_keyboard())
            return

        # ── Домашка: ввод текста ──
        if step == "hw_input":
            if ":" in text:
                parts = text.split(":", 1)
                subj = parts[0].strip()
                desc = parts[1].strip()
                DATA["homework"].setdefault(uid_s, []).append(
                    {"subject": subj, "desc": desc, "done": False})
                save_data()
                del user_state[uid]
                add_points(uid_s, 10)
                send_message(uid, f"✅ ДЗ по «{subj}» добавлено! +10 баллов! 🎉",
                             homework_keyboard())
            else:
                send_message(uid,
                    "Формат: Предмет: что задали\n"
                    "Пример: Математика: стр. 45 № 3,4")
            return

        # ── Домашка: отметка выполнения ──
        if step == "hw_done":
            hw_list = DATA.get("homework", {}).get(uid_s, [])
            try:
                num = int(text) - 1
                if 0 <= num < len(hw_list):
                    hw_list[num]["done"] = True
                    save_data()
                    del user_state[uid]
                    add_points(uid_s, 15)
                    send_message(uid, "✅ Отлично! +15 баллов! 🎉",
                                 homework_keyboard())
                    return
            except ValueError:
                pass
            send_message(uid, "Напиши номер ДЗ цифрой:")
            return

        # ── Домашка: удаление ──
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

        # ── Оценки: ввод ──
        if step == "grade_input":
            if ":" in text:
                parts = text.split(":", 1)
                subj = parts[0].strip()
                val = parts[1].strip()
                DATA["grades"].setdefault(uid_s, []).append({
                    "subject": subj,
                    "grade": val,
                    "date": datetime.now().strftime("%d.%m"),
                })
                save_data()
                del user_state[uid]
                add_points(uid_s, 10)
                send_message(uid,
                    f"✅ Оценка {val} по «{subj}» добавлена! +10 баллов! 🎉",
                    grades_keyboard())
            else:
                send_message(uid,
                    "Формат: Предмет: оценка\nПример: Алгебра: 4")
            return

    # ═══════════════════════════════════════════════════
    #  ОСНОВНОЕ МЕНЮ
    # ═══════════════════════════════════════════════════

    text_lower = text.lower()

    # ── Старт / приветствие ──
    if text_lower in ["начало", "начать", "привет", "меню",
                      "🏠 главное меню", "старт"]:
        send_message(uid,
            "Привет! Я «Навигатор Успеха» v3.0 🎯\n\n"
            "Что нового:\n"
            "🤖 ИИ-тьютор — объясняет темы простыми словами\n"
            "📊 Анализ нагрузки — помогает планировать неделю\n"
            "📈 Трекинг прогресса — карта твоих запросов\n"
            "🎯 Геймификация — баллы и уровни за активность\n\n"
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
                "Расписание ещё не настроено. Нажми «Настроить расписание»!",
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
            "• «приставки ПРЕ и ПРИ»\n"
            "• «как работают глаголы»\n\n"
            "Я объясню на примерах и задам проверочный вопрос 🎯",
            ai_keyboard())
        return

    if text == "📝 Спросить ИИ-тьютора":
        user_state[uid] = {"step": "ai_input"}
        send_message(uid, "Напиши тему, которую хочешь понять 👇", None)
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
            f"Напоминания {status}.\n\n"
            "Я напоминаю за 15 минут до каждого урока, кружка, "
            "секции или репетиции.",
            reminders_keyboard())
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

    if text == "📋 Мои напоминания сегодня":
        week = DATA.get("schedules", {}).get(uid_s, {}).get("week", {})
        today = get_today_key()
        items = week.get(today, [])
        if not items:
            send_message(uid, "Сегодня нет запланированных занятий.",
                         reminders_keyboard())
        else:
            sorted_items = sorted(items, key=lambda x: x.get("time", "99:99"))
            lines = ["📋 Сегодня напоминаю о:"]
            for item in sorted_items:
                icon = "🎯" if item.get("type") == "extra" else "📖"
                lines.append(
                    f"  {item['time']} {icon} {item['subject']} "
                    f"→ напомну в {_minus_15(item['time'])}")
            send_message(uid, "\n".join(lines), reminders_keyboard())
        return

    # ── Домашка ──
    if text == "📝 Домашка":
        send_message(uid, "Управление домашними заданиями:", homework_keyboard())
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
            send_message(uid, "Домашки нет! Можно отдохнуть 😎", homework_keyboard())
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
            lines.append(f"\n📈 Общий средний: {sum(total_nums) / len(total_nums):.2f}")
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

    # ── ЦОК: категории ──
    if text == "📚 Учёба (ЦОК)":
        send_message(uid, "Выбери категорию предметов:", categories_keyboard())
        return

    for cat in SUBJECT_CATEGORIES:
        if text == f"📁 {cat}":
            send_message(uid, f"Предметы категории «{cat}»:", subjects_keyboard(cat))
            return

    if text == "⬅️ К категориям":
        send_message(uid, "Выбери категорию:", categories_keyboard())
        return

    # ── ЦОК: клик по предмету ──
    if text in ALL_COK_SUBJECTS:
        user_state[uid] = {"step": "cok_subject", "subject": text}
        send_message(uid,
            f"📖 Предмет: {text}\n\nЧто делаем?",
            cok_subject_keyboard())
        return

    # ── Мотивация ──
    if text == "⭐ Мотивация":
        send_message(uid, random.choice(MORNING_QUOTES), main_keyboard())
        return

    if text == "💡 Совет дня":
        send_message(uid, random.choice(STUDY_TIPS), main_keyboard())
        return

    # ── Помощь ──
    if text == "ℹ️ Помощь":
        send_message(uid,
            "🤖 Навигатор Успеха v3.0\n\n"
            "Что я умею:\n"
            "🤖 ИИ-тьютор — объясняю темы простыми словами\n"
            "📅 Расписание — настрой на неделю, я напомню\n"
            "📝 Домашка — список заданий, отметка о выполнении\n"
            "⏰ Напоминания — автоматические за 15 минут до урока/секции\n"
            "🏆 Оценки — журнал и средний балл\n"
            "📊 Анализ недели — где перегрузка, как планировать\n"
            "📈 Мой прогресс — карта запросов к ИИ\n"
            "🎯 Мой уровень — баллы за активность\n"
            "📚 Учёба (ЦОК) — навигация по предметам\n\n"
            "Начни с настройки расписания!",
            main_keyboard())
        return

    if text == "⬅️ Назад":
        send_message(uid, "Главное меню:", main_keyboard())
        return

    # ── Текстовые команды: «объясни ...» ──
    if text_lower.startswith("объясни") or text_lower.startswith("не понял") or \
       text_lower.startswith("не понимаю"):
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
            add_points(uid_s, 20)
            pts = points_info(uid_s)
            send_message(uid,
                f"🤖 ИИ-тьютор:\n\n{explanation}\n\n---\n{pts} (+20 баллов! 🎉)",
                ai_keyboard())
            return

    # ── Не распознано ──
    send_message(uid, "Нажми на кнопку в меню — я всё покажу! 👇",
                 main_keyboard())


# ═══════════════════════════════════════════════════════
#  ЗАПУСК БОТА
# ═══════════════════════════════════════════════════════

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()

vk_rem_session = vk_api.VkApi(token=TOKEN)
vk_rem = vk_rem_session.get_api()

longpoll = VkLongPoll(vk_session)

threading.Thread(target=reminder_loop, daemon=True).start()

print("=" * 50)
print("  Навигатор Успеха v3.0")
print("  ИИ-тьютор + аналитика + геймификация")
print("  Бот запущен! ✅")
print("=" * 50)

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        handle_message(event)
