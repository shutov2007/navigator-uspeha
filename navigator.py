#!/usr/bin/env python3
"""
Навигатор Успеха v3.0 — чат-бот для ВКонтакте.
Помогает школьнику организовать время, напоминает о событиях,
даёт ссылки на учебные материалы ЦОК, отслеживает оценки
и мотивирует на достижения.

Для конкурса «Технологии Первых» 2026.
Автор: [Святослав Шутов], г. Мамоново, Калининградская область.
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import random
import time
import re
import threading
from datetime import datetime, timedelta

# --- ПРОВЕРКА ТОКЕНА ---
TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    print("=" * 60)
    print("ОШИБКА: Переменная окружения VK_TOKEN не найдена!")
    print("Добавьте её в панели Bothost:")
    print("  Имя: VK_TOKEN")
    print("  Значение: токен вашего сообщества ВКонтакте")
    print("=" * 60)
    sys.exit(1)

try:
    import vk_api
    from vk_api.longpoll import VkLongPoll, VkEventType
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
except ImportError:
    print("ОШИБКА: библиотека vk_api не установлена!")
    print("Убедитесь, что в requirements.txt указано: vk_api==11.9.9")
    sys.exit(1)


# ============================================================
#  КОНСТАНТЫ И ДАННЫЕ
# ============================================================

VERSION = "3.0"
BOT_NAME = "Навигатор Успеха"

DAYS_OF_WEEK = [
    "Понедельник", "Вторник", "Среда",
    "Четверг", "Пятница", "Суббота", "Воскресенье",
]

DAYS_SHORT = {
    "понедельник": "Понедельник", "пн": "Понедельник",
    "вторник": "Вторник", "вт": "Вторник",
    "среда": "Среда", "ср": "Среда",
    "четверг": "Четверг", "чт": "Четверг",
    "пятница": "Пятница", "пт": "Пятница",
    "суббота": "Суббота", "сб": "Суббота",
    "воскресенье": "Воскресенье", "вс": "Воскресенье",
}

SUBJECT_CATEGORIES = {
    "Основные": [
        "Математика", "Алгебра", "Геометрия",
        "Русский язык", "Литература", "Английский язык",
    ],
    "Естественные": [
        "Физика", "Химия", "Биология",
        "География", "Информатика",
    ],
    "Гуманитарные": [
        "История", "Обществознание",
        "Окружающий мир", "Литературное чтение",
    ],
    "Творчество и спорт": [
        "ИЗО", "Музыка", "Технология",
        "Физкультура", "ОБЖ",
    ],
}

MORNING_QUOTES = [
    "Дорогу осилит идущий! Удачного дня! 🌅",
    "Сегодня отличный день, чтобы узнать что-то новое! 📖",
    "Маленькие шаги ведут к большим целям. Дерзай! 🎯",
    "Ты умнее, чем думаешь. Верь в себя! 💪",
    "Знания — это суперсила. Используй её сегодня! ⚡",
    "Не бойся ошибаться — бойся ничего не делать! 🚀",
    "Каждый эксперт когда-то был новичком. Продолжай! 🌟",
    "Учись так, чтобы завтра ты был лучше, чем вчера! 📈",
    "Терпение и труд всё перетрут. Не сдавайся! 🔥",
    "Твой прогресс зависит от твоих усилий. Действуй! ⚡",
]

STUDY_TIPS = [
    "💡 Совет: читай учебник с карандашом — отмечай главное прямо в тексте.",
    "💡 Совет: объясни новую тему кому-то — так ты поймёшь её лучше.",
    "💡 Совет: делай домашку в тишине, без телефона рядом. 25 минут работы, 5 отдыха — техника Pomodoro.",
    "💡 Совет: повторяй материал перед сном — мозг лучше запомнит во сне.",
    "💡 Совет: рисуй схемы и таблицы — визуализация помогает запоминать.",
    "💡 Совет: не откладывай на завтра. Сделай маленькую часть прямо сейчас.",
    "💡 Совет: делай перерывы каждые 30-40 минут. Мозгу нужно отдыхать.",
    "💡 Совет: пей воду во время занятий — это помогает концентрации.",
    "💡 Совет: составляй план на день с вечера — так легче начать утро.",
    "💡 Совет: используй карточки для запоминания терминов и дат.",
]

MOTIVATION_STORIES = [
    ("Томас Эдисон", "Эдисон провёл более 1000 экспериментов, прежде чем создал рабочую лампу. "
     "Когда его спросили о неудачах, он ответил: «Я не проиграл — я нашёл 1000 способов, которые не работают»."),
    ("Уолт Дисней", "Диснея уволили из газеты за «недостаток воображения». Позже он создал самую "
     "известную анимационную студию в мире."),
    ("Альберт Эйнштейн", "Учителя считали Эйнштейна медлительным и неспособным. "
     "А он стал одним из величайших физиков в истории."),
    ("Джоан Роулинг", "Рукопись «Гарри Поттера» отклонили 12 издательств. "
     "А потом книга стала бестселлером во всём мире."),
    ("Михаил Ломоносов", "Сын рыбака из Архангельской губернии пешкой дошёл до Москвы, "
     "чтобы учиться. Стал великим русским учёным."),
]

EDUCATIONAL_LINKS = {
    "Математика": [
        ("Учи.ру — интерактивные задания", "https://uchi.ru"),
        ("Яндекс.Учебник — математика", "https://education.yandex.ru"),
        ("Skysmart — онлайн-уроки", "https://skysmart.ru"),
    ],
    "Русский язык": [
        ("Учи.ру — русский язык", "https://uchi.ru"),
        ("Грамота.ру — справочная служба", "https://gramota.ru"),
        ("Яндекс.Учебник — русский", "https://education.yandex.ru"),
    ],
    "Английский язык": [
        ("Duolingo — изучение языков", "https://duolingo.com"),
        ("Lingualeo — английский онлайн", "https://lingualeo.com"),
    ],
    "Физика": [
        ("Skysmart — физика", "https://skysmart.ru"),
        ("Элементы — наука", "https://elementy.ru"),
    ],
    "Информатика": [
        ("Code.org — основы программирования", "https://code.org"),
        ("Stepik — курсы", "https://stepik.org"),
    ],
    "История": [
        ("Арзамас — истории", "https://arzamas.academy"),
        ("История.РФ — портал", "https://histrf.ru"),
    ],
    "Биология": [
        ("Биомолекула — наука о жизни", "https://biomolecula.ru"),
        ("Учи.ру — окружающий мир", "https://uchi.ru"),
    ],
    "Химия": [
        ("Skysmart — химия", "https://skysmart.ru"),
        ("Химик — таблица Менделеева", "https://chemister.ru"),
    ],
    "География": [
        ("Яндекс.Карты", "https://yandex.ru/maps"),
        ("Учи.ру — география", "https://uchi.ru"),
    ],
    "Литература": [
        ("Флибуста — книги", "https://flibusta.is"),
        ("Литрес — аудиокниги", "https://litres.ru"),
    ],
    "Обществознание": [
        ("Stepik — обществознание", "https://stepik.org"),
        ("Skysmart — обществознание", "https://skysmart.ru"),
    ],
    "Алгебра": [
        ("Skysmart — алгебра", "https://skysmart.ru"),
        ("Учи.ру — математика", "https://uchi.ru"),
    ],
    "Геометрия": [
        ("Skysmart — геометрия", "https://skysmart.ru"),
        ("Учи.ру — математика", "https://uchi.ru"),
    ],
}

DEFAULT_LINKS = [
    ("Учи.ру — интерактивная школа", "https://uchi.ru"),
    ("Яндекс.Учебник", "https://education.yandex.ru"),
    ("Skysmart — онлайн-школа", "https://skysmart.ru"),
    ("Stepik — онлайн-курсы", "https://stepik.org"),
]


# ============================================================
#  ХРАНИЛИЩЕ ДАННЫХ (в памяти)
# ============================================================

user_data = {}
user_states = {}
last_message_time = {}
original_texts = {}
MIN_INTERVAL = 1


def get_user_data(user_id):
    """Получить данные пользователя или создать пустые."""
    if user_id not in user_data:
        user_data[user_id] = {
            "schedules": {},
            "homework": [],
            "reminders": [],
            "grades": {},
            "goals": [],
            "last_quote_date": None,
            "name": None,
        }
    return user_data[user_id]


# ============================================================
#  КЛАВИАТУРЫ
# ============================================================

def build_keyboard(rows, one_time=False):
    """Безопасно строит клавиатуру из списка строк.
    Каждая строка — список (текст, цвет)."""
    kb = VkKeyboard(one_time=one_time)
    for row_idx, row in enumerate(rows):
        for label, color in row:
            kb.add_button(label, color=color)
        if row_idx < len(rows) - 1:
            kb.add_line()
    return kb.get_keyboard()


def main_menu_kb():
    return build_keyboard([
        [("📅 Расписание", VkKeyboardColor.PRIMARY),
         ("📝 Домашка", VkKeyboardColor.PRIMARY)],
        [("⏰ Напоминания", VkKeyboardColor.PRIMARY),
         ("🏆 Оценки", VkKeyboardColor.POSITIVE)],
        [("📚 Учёба (ЦОК)", VkKeyboardColor.POSITIVE),
         ("🎯 Цели недели", VkKeyboardColor.POSITIVE)],
        [("⭐ Мотивация", VkKeyboardColor.SECONDARY),
         ("💡 Совет дня", VkKeyboardColor.SECONDARY)],
        [("ℹ️ Помощь", VkKeyboardColor.SECONDARY)],
    ])


def schedule_menu_kb():
    return build_keyboard([
        [("➕ Добавить урок", VkKeyboardColor.PRIMARY),
         ("📋 Показать расписание", VkKeyboardColor.PRIMARY)],
        [("🗑 Удалить расписание дня", VkKeyboardColor.NEGATIVE)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def homework_menu_kb():
    return build_keyboard([
        [("➕ Добавить задание", VkKeyboardColor.PRIMARY),
         ("📋 Показать задания", VkKeyboardColor.PRIMARY)],
        [("🗑 Удалить задание", VkKeyboardColor.NEGATIVE)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def reminders_menu_kb():
    return build_keyboard([
        [("➕ Добавить напоминание", VkKeyboardColor.PRIMARY),
         ("📋 Показать напоминания", VkKeyboardColor.PRIMARY)],
        [("🗑 Удалить напоминание", VkKeyboardColor.NEGATIVE)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def grades_menu_kb():
    return build_keyboard([
        [("➕ Добавить оценку", VkKeyboardColor.PRIMARY),
         ("📋 Показать оценки", VkKeyboardColor.PRIMARY)],
        [("📊 Средний балл", VkKeyboardColor.POSITIVE)],
        [("🗑 Очистить предмет", VkKeyboardColor.NEGATIVE)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def goals_menu_kb():
    return build_keyboard([
        [("➕ Поставить цель", VkKeyboardColor.PRIMARY),
         ("📋 Мои цели", VkKeyboardColor.PRIMARY)],
        [("✅ Отметить выполнение", VkKeyboardColor.POSITIVE)],
        [("🗑 Удалить цель", VkKeyboardColor.NEGATIVE)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def study_menu_kb():
    return build_keyboard([
        [("📁 Основные", VkKeyboardColor.PRIMARY),
         ("📁 Естественные", VkKeyboardColor.PRIMARY)],
        [("📁 Гуманитарные", VkKeyboardColor.PRIMARY),
         ("📁 Творчество и спорт", VkKeyboardColor.PRIMARY)],
        [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
    ])


def subjects_kb(category):
    subjects = SUBJECT_CATEGORIES.get(category, [])
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for subj in subjects[i:i + 2]:
            row.append((subj, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([
        ("⬅️ К категориям", VkKeyboardColor.SECONDARY),
        ("🏠 Главное меню", VkKeyboardColor.SECONDARY),
    ])
    return build_keyboard(rows)


def days_kb():
    rows = []
    for i in range(0, len(DAYS_OF_WEEK), 2):
        row = []
        for d in DAYS_OF_WEEK[i:i + 2]:
            row.append((d, VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def cancel_kb():
    return build_keyboard([
        [("❌ Отмена", VkKeyboardColor.NEGATIVE)],
    ])


def goals_list_kb(goals):
    rows = []
    for i, goal in enumerate(goals):
        mark = "✅" if goal.get("done") else "⬜"
        label = f"{mark} {i + 1}. {goal['text'][:30]}"
        rows.append([(label, VkKeyboardColor.SECONDARY)])
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def homework_list_kb(homework):
    rows = []
    for i, hw in enumerate(homework):
        label = f"{i + 1}. {hw['subject']} — {hw['text'][:25]}"
        rows.append([(label, VkKeyboardColor.SECONDARY)])
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def grades_subjects_kb(grades):
    subjects = list(grades.keys())
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for s in subjects[i:i + 2]:
            row.append((s, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def schedule_days_kb(schedules):
    days = list(schedules.keys())
    if not days:
        return build_keyboard([
            [("⬅️ Назад", VkKeyboardColor.SECONDARY)],
        ])
    rows = []
    for d in days:
        rows.append([(f"🗑 {d}", VkKeyboardColor.NEGATIVE)])
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


def reminders_list_kb(reminders):
    rows = []
    for i, rem in enumerate(reminders):
        label = f"{i + 1}. {rem['text'][:30]}"
        rows.append([(label, VkKeyboardColor.SECONDARY)])
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)


# ============================================================
#  ОТПРАВКА СООБЩЕНИЙ
# ============================================================

def send_msg(user_id, text, keyboard=None):
    """Отправка сообщения с защитой от частых запросов."""
    now = time.time()
    if user_id in last_message_time:
        if now - last_message_time[user_id] < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL)
    last_message_time[user_id] = now

    try:
        kwargs = {
            "user_id": user_id,
            "message": text,
            "random_id": random.randint(0, 2 ** 31 - 1),
        }
        if keyboard is not None:
            kwargs["keyboard"] = keyboard
        vk.messages.send(**kwargs)
    except vk_api.exceptions.ApiError as e:
        print(f"[VK API ERROR] user={user_id}: {e}")
    except Exception as e:
        print(f"[SEND ERROR] user={user_id}: {e}")


# ============================================================
#  УПРАВЛЕНИЕ СОСТОЯНИЯМИ
# ============================================================

def set_state(user_id, state, data=None):
    user_states[user_id] = {"state": state, "data": data or {}}


def get_state(user_id):
    return user_states.get(user_id)


def clear_state(user_id):
    if user_id in user_states:
        del user_states[user_id]


# ============================================================
#  ХЕЛПЕРЫ
# ============================================================

def get_original_text(user_id, lower_text):
    """Возвращает оригинальный текст (с заглавными), если сохранён."""
    return original_texts.get(user_id, lower_text)


def parse_day(text):
    """Парсит день недели из текста. Возвращает название или None."""
    for d in DAYS_OF_WEEK:
        if text == d.lower():
            return d
    return DAYS_SHORT.get(text)


# ============================================================
#  ОБРАБОТЧИКИ — ГЛАВНОЕ МЕНЮ
# ============================================================

def handle_main_menu(user_id, text):
    """Обработка кнопок главного меню."""
    if text in ("начать", "меню", "🏠 главное меню", "/start", "start",
                "привет", "hi", "hello", "привет!", "здравствуй"):
        data = get_user_data(user_id)
        name = data.get("name")
        greeting = "Привет! 👋\n\n"
        greeting += f"Я «{BOT_NAME}» — твой помощник в учёбе.\n"
        greeting += "Выбери, что нужно:"
        send_msg(user_id, greeting, main_menu_kb())
        return True

    if text == "📅 расписание":
        send_msg(user_id, "📅 Расписание уроков\n\nЧто сделать?", schedule_menu_kb())
        return True

    if text == "📝 домашка":
        send_msg(user_id, "📝 Домашние задания\n\nЧто сделать?", homework_menu_kb())
        return True

    if text == "⏰ напоминания":
        send_msg(user_id, "⏰ Напоминания\n\nЧто сделать?", reminders_menu_kb())
        return True

    if text == "🏆 оценки":
        send_msg(user_id, "🏆 Оценки\n\nЧто сделать?", grades_menu_kb())
        return True

    if text == "📚 учёба (цок)":
        send_msg(user_id, "📚 Учебные материалы\n\nВыбери категорию:", study_menu_kb())
        return True

    if text == "🎯 цели недели":
        send_msg(user_id, "🎯 Цели недели\n\nЧто сделать?", goals_menu_kb())
        return True

    if text == "⭐ мотивация":
        handle_motivation(user_id)
        return True

    if text == "💡 совет дня":
        handle_tip(user_id)
        return True

    if text == "ℹ️ помощь":
        handle_help(user_id)
        return True

    return False


# ============================================================
#  ОБРАБОТЧИКИ — РАСПИСАНИЕ
# ============================================================

def handle_schedule_menu(user_id, text):
    if text == "➕ добавить урок":
        send_msg(user_id, "Выбери день недели:", days_kb())
        set_state(user_id, "schedule_day")
        return True

    if text == "📋 показать расписание":
        handle_schedule_show(user_id)
        return True

    if text == "🗑 удалить расписание дня":
        data = get_user_data(user_id)
        if not data["schedules"]:
            send_msg(user_id, "Расписание пока пустое. Добавь уроки сначала!",
                     schedule_menu_kb())
            return True
        send_msg(user_id, "Выбери день для удаления:",
                 schedule_days_kb(data["schedules"]))
        set_state(user_id, "schedule_delete_day")
        return True

    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    return False


def handle_schedule_day(user_id, text):
    """Пользователь выбрал день — спрашиваем предмет."""
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Расписание:", schedule_menu_kb())
        return True

    day = parse_day(text)
    if not day:
        send_msg(user_id, "Не понял день. Выбери из кнопок:", days_kb())
        return True

    set_state(user_id, "schedule_subject", {"day": day})
    send_msg(user_id,
             f"День: {day}\n\nВведи название предмета (например, «Математика»):",
             cancel_kb())
    return True


def handle_schedule_subject(user_id, text):
    state = get_state(user_id)
    if not state or state["state"] != "schedule_subject":
        return False

    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Расписание:", schedule_menu_kb())
        return True

    day = state["data"]["day"]
    subject = get_original_text(user_id, text)

    data = get_user_data(user_id)
    if day not in data["schedules"]:
        data["schedules"][day] = []
    data["schedules"][day].append(subject)

    clear_state(user_id)
    send_msg(user_id,
             f"✅ Урок «{subject}» добавлен в {day}!",
             schedule_menu_kb())
    return True


def handle_schedule_delete_day(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Расписание:", schedule_menu_kb())
        return True

    data = get_user_data(user_id)
    day_text = text.replace("🗑", "").strip()
    day = parse_day(day_text)
    if day and day in data["schedules"]:
        del data["schedules"][day]
        clear_state(user_id)
        send_msg(user_id, f"✅ Расписание на {day} удалено!",
                 schedule_menu_kb())
        return True

    send_msg(user_id, "Не нашёл такой день. Попробуй ещё раз.",
             schedule_menu_kb())
    return True


def handle_schedule_show(user_id):
    data = get_user_data(user_id)
    if not data["schedules"]:
        send_msg(user_id, "Расписание пока пустое. Добавь уроки!",
                 schedule_menu_kb())
        return

    msg = "📅 Твоё расписание:\n\n"
    for day in DAYS_OF_WEEK:
        if day in data["schedules"] and data["schedules"][day]:
            lessons = data["schedules"][day]
            msg += f"📌 {day}:\n"
            for i, subj in enumerate(lessons, 1):
                msg += f"   {i}. {subj}\n"
            msg += "\n"
    send_msg(user_id, msg, schedule_menu_kb())


# ============================================================
#  ОБРАБОТЧИКИ — ДОМАШНИЕ ЗАДАНИЯ
# ============================================================

def handle_homework_menu(user_id, text):
    if text == "➕ добавить задание":
        set_state(user_id, "hw_subject")
        send_msg(user_id, "Введи предмет (например, «Математика»):",
                 cancel_kb())
        return True

    if text == "📋 показать задания":
        handle_homework_show(user_id)
        return True

    if text == "🗑 удалить задание":
        data = get_user_data(user_id)
        if not data["homework"]:
            send_msg(user_id, "Заданий пока нет.", homework_menu_kb())
            return True
        send_msg(user_id, "Выбери задание для удаления:",
                 homework_list_kb(data["homework"]))
        set_state(user_id, "hw_delete")
        return True

    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    return False


def handle_homework_subject(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Домашка:", homework_menu_kb())
        return True

    subject = get_original_text(user_id, text)
    set_state(user_id, "hw_text", {"subject": subject})
    send_msg(user_id,
             f"Предмет: {subject}\n\nВведи текст задания:",
             cancel_kb())
    return True


def handle_homework_text(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Домашка:", homework_menu_kb())
        return True

    state = get_state(user_id)
    subject = state["data"]["subject"]
    hw_text = get_original_text(user_id, text)

    data = get_user_data(user_id)
    data["homework"].append({
        "subject": subject,
        "text": hw_text,
        "date": datetime.now().strftime("%d.%m.%Y"),
    })

    clear_state(user_id)
    send_msg(user_id,
             f"✅ Задание добавлено!\nПредмет: {subject}\nЗадание: {hw_text}",
             homework_menu_kb())
    return True


def handle_homework_show(user_id):
    data = get_user_data(user_id)
    if not data["homework"]:
        send_msg(user_id, "Заданий пока нет. Добавь новое!",
                 homework_menu_kb())
        return

    msg = "📝 Твои домашние задания:\n\n"
    for i, hw in enumerate(data["homework"], 1):
        msg += f"{i}. 📚 {hw['subject']}\n"
        msg += f"   {hw['text']}\n"
        msg += f"   📅 {hw['date']}\n\n"
    send_msg(user_id, msg, homework_menu_kb())


def handle_homework_delete(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Домашка:", homework_menu_kb())
        return True

    data = get_user_data(user_id)
    match = re.match(r"(\d+)\.", text)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(data["homework"]):
            removed = data["homework"].pop(idx)
            clear_state(user_id)
            send_msg(user_id,
                     f"✅ Удалено: {removed['subject']} — {removed['text']}",
                     homework_menu_kb())
            return True

    send_msg(user_id, "Не нашёл задание. Попробуй ещё раз.",
             homework_menu_kb())
    return True


# ============================================================
#  ОБРАБОТЧИКИ — НАПОМИНАНИЯ
# ============================================================

def handle_reminders_menu(user_id, text):
    if text == "➕ добавить напоминание":
        set_state(user_id, "reminder_text")
        send_msg(user_id, "Введи текст напоминания:", cancel_kb())
        return True

    if text == "📋 показать напоминания":
        handle_reminders_show(user_id)
        return True

    if text == "🗑 удалить напоминание":
        data = get_user_data(user_id)
        if not data["reminders"]:
            send_msg(user_id, "Напоминаний пока нет.", reminders_menu_kb())
            return True
        send_msg(user_id, "Выбери напоминание для удаления:",
                 reminders_list_kb(data["reminders"]))
        set_state(user_id, "reminder_delete")
        return True

    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    return False


def handle_reminder_text(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Напоминания:", reminders_menu_kb())
        return True

    rem_text = get_original_text(user_id, text)
    data = get_user_data(user_id)
    data["reminders"].append({
        "text": rem_text,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
    })

    clear_state(user_id)
    send_msg(user_id,
             f"✅ Напоминание добавлено:\n{rem_text}",
             reminders_menu_kb())
    return True


def handle_reminders_show(user_id):
    data = get_user_data(user_id)
    if not data["reminders"]:
        send_msg(user_id, "Напоминаний пока нет.", reminders_menu_kb())
        return

    msg = "⏰ Твои напоминания:\n\n"
    for i, rem in enumerate(data["reminders"], 1):
        msg += f"{i}. {rem['text']}\n   📅 {rem['date']}\n\n"
    send_msg(user_id, msg, reminders_menu_kb())


def handle_reminder_delete(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Напоминания:", reminders_menu_kb())
        return True

    data = get_user_data(user_id)
    match = re.match(r"(\d+)\.", text)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(data["reminders"]):
            removed = data["reminders"].pop(idx)
            clear_state(user_id)
            send_msg(user_id,
                     f"✅ Удалено: {removed['text']}",
                     reminders_menu_kb())
            return True

    send_msg(user_id, "Не нашёл напоминание.", reminders_menu_kb())
    return True


# ============================================================
#  ОБРАБОТЧИКИ — ОЦЕНКИ
# ============================================================

def handle_grades_menu(user_id, text):
    if text == "➕ добавить оценку":
        set_state(user_id, "grade_subject")
        send_msg(user_id, "Введи предмет:", cancel_kb())
        return True

    if text == "📋 показать оценки":
        handle_grades_show(user_id)
        return True

    if text == "📊 средний балл":
        handle_grades_average(user_id)
        return True

    if text == "🗑 очистить предмет":
        data = get_user_data(user_id)
        if not data["grades"]:
            send_msg(user_id, "Оценок пока нет.", grades_menu_kb())
            return True
        send_msg(user_id, "Выбери предмет для очистки:",
                 grades_subjects_kb(data["grades"]))
        set_state(user_id, "grade_clear")
        return True

    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    return False


def handle_grade_subject(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Оценки:", grades_menu_kb())
        return True

    subject = get_original_text(user_id, text)
    set_state(user_id, "grade_value", {"subject": subject})
    send_msg(user_id,
             f"Предмет: {subject}\n\nВведи оценку (от 1 до 5):",
             cancel_kb())
    return True


def handle_grade_value(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Оценки:", grades_menu_kb())
        return True

    state = get_state(user_id)
    subject = state["data"]["subject"]

    try:
        grade = int(text.strip())
    except ValueError:
        send_msg(user_id, "Введи число от 1 до 5:", cancel_kb())
        return True

    if grade < 1 or grade > 5:
        send_msg(user_id, "Оценка должна быть от 1 до 5!", cancel_kb())
        return True

    data = get_user_data(user_id)
    if subject not in data["grades"]:
        data["grades"][subject] = []
    data["grades"][subject].append({
        "grade": grade,
        "date": datetime.now().strftime("%d.%m.%Y"),
    })

    clear_state(user_id)
    send_msg(user_id,
             f"✅ Оценка {grade} по предмету «{subject}» добавлена!",
             grades_menu_kb())
    return True


def handle_grades_show(user_id):
    data = get_user_data(user_id)
    if not data["grades"]:
        send_msg(user_id, "Оценок пока нет. Добавь первую!",
                 grades_menu_kb())
        return

    msg = "🏆 Твои оценки:\n\n"
    for subject, grades in data["grades"].items():
        grades_str = ", ".join(str(g["grade"]) for g in grades)
        msg += f"📚 {subject}: {grades_str}\n"
    send_msg(user_id, msg, grades_menu_kb())


def handle_grades_average(user_id):
    data = get_user_data(user_id)
    if not data["grades"]:
        send_msg(user_id, "Оценок пока нет. Добавь хотя бы одну!",
                 grades_menu_kb())
        return

    msg = "📊 Средний балл по предметам:\n\n"
    total_sum = 0
    total_count = 0
    for subject, grades in data["grades"].items():
        if grades:
            s = sum(g["grade"] for g in grades)
            c = len(grades)
            avg = s / c
            total_sum += s
            total_count += c
            msg += f"📚 {subject}: {avg:.2f} (оценок: {c})\n"

    if total_count > 0:
        overall = total_sum / total_count
        msg += f"\n📌 Общий средний балл: {overall:.2f}"
    send_msg(user_id, msg, grades_menu_kb())


def handle_grade_clear(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Оценки:", grades_menu_kb())
        return True

    data = get_user_data(user_id)
    subject = get_original_text(user_id, text)
    if subject in data["grades"]:
        del data["grades"][subject]
        clear_state(user_id)
        send_msg(user_id, f"✅ Оценки по «{subject}» очищены!",
                 grades_menu_kb())
        return True

    send_msg(user_id, "Не нашёл предмет.", grades_menu_kb())
    return True


# ============================================================
#  ОБРАБОТЧИКИ — ЦЕЛИ НЕДЕЛИ
# ============================================================

def handle_goals_menu(user_id, text):
    if text == "➕ поставить цель":
        set_state(user_id, "goal_add")
        send_msg(user_id, "Введи текст цели:", cancel_kb())
        return True

    if text == "📋 мои цели":
        handle_goals_show(user_id)
        return True

    if text == "✅ отметить выполнение":
        data = get_user_data(user_id)
        if not data["goals"]:
            send_msg(user_id, "Целей пока нет.", goals_menu_kb())
            return True
        send_msg(user_id, "Выбери цель:", goals_list_kb(data["goals"]))
        set_state(user_id, "goal_done")
        return True

    if text == "🗑 удалить цель":
        data = get_user_data(user_id)
        if not data["goals"]:
            send_msg(user_id, "Целей пока нет.", goals_menu_kb())
            return True
        send_msg(user_id, "Выбери цель для удаления:",
                 goals_list_kb(data["goals"]))
        set_state(user_id, "goal_delete")
        return True

    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    return False


def handle_goal_add(user_id, text):
    if text == "❌ отмена":
        clear_state(user_id)
        send_msg(user_id, "Отменено. Цели:", goals_menu_kb())
        return True

    goal_text = get_original_text(user_id, text)
    data = get_user_data(user_id)
    data["goals"].append({"text": goal_text, "done": False})

    clear_state(user_id)
    send_msg(user_id,
             f"✅ Цель добавлена: {goal_text}",
             goals_menu_kb())
    return True


def handle_goals_show(user_id):
    data = get_user_data(user_id)
    if not data["goals"]:
        send_msg(user_id, "Целей пока нет. Поставь первую!",
                 goals_menu_kb())
        return

    msg = "🎯 Твои цели на неделю:\n\n"
    for i, goal in enumerate(data["goals"], 1):
        mark = "✅" if goal["done"] else "⬜"
        msg += f"{mark} {i}. {goal['text']}\n"
    done_count = sum(1 for g in data["goals"] if g["done"])
    msg += f"\n📊 Выполнено: {done_count} из {len(data['goals'])}"
    send_msg(user_id, msg, goals_menu_kb())


def handle_goal_done(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Цели:", goals_menu_kb())
        return True

    data = get_user_data(user_id)
    match = re.match(r"[✅⬜]\s*(\d+)\.", text)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(data["goals"]):
            data["goals"][idx]["done"] = not data["goals"][idx]["done"]
            status = ("✅ выполнено" if data["goals"][idx]["done"]
                      else "⬜ не выполнено")
            clear_state(user_id)
            send_msg(user_id,
                     f"Статус изменён: {status}\n"
                     f"Цель: {data['goals'][idx]['text']}",
                     goals_menu_kb())
            return True

    send_msg(user_id, "Не нашёл цель.", goals_menu_kb())
    return True


def handle_goal_delete(user_id, text):
    if text == "⬅️ назад":
        clear_state(user_id)
        send_msg(user_id, "Цели:", goals_menu_kb())
        return True

    data = get_user_data(user_id)
    match = re.match(r"[✅⬜]\s*(\d+)\.", text)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(data["goals"]):
            removed = data["goals"].pop(idx)
            clear_state(user_id)
            send_msg(user_id,
                     f"✅ Удалено: {removed['text']}",
                     goals_menu_kb())
            return True

    send_msg(user_id, "Не нашёл цель.", goals_menu_kb())
    return True


# ============================================================
#  ОБРАБОТЧИКИ — УЧЕБНЫЕ МАТЕРИАЛЫ (ЦОК)
# ============================================================

def handle_study_menu(user_id, text):
    # Кнопка "Назад"
    if text == "⬅️ назад":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    # Кнопка "К категориям"
    if text == "⬅️ к категориям":
        send_msg(user_id, "Выбери категорию:", study_menu_kb())
        return True

    # Кнопка "Главное меню"
    if text == "🏠 главное меню":
        send_msg(user_id, "Главное меню:", main_menu_kb())
        return True

    # Категории
    for cat in SUBJECT_CATEGORIES:
        if text == f"📁 {cat.lower()}":
            send_msg(user_id,
                     f"Предметы категории «{cat}»:\nВыбери предмет:",
                     subjects_kb(cat))
            return True

    # Проверяем, не предмет ли это
    for cat, subjects in SUBJECT_CATEGORIES.items():
        for subj in subjects:
            if text == subj.lower():
                handle_study_subject(user_id, subj)
                return True

    return False


def handle_study_subject(user_id, subject):
    links = EDUCATIONAL_LINKS.get(subject, DEFAULT_LINKS)
    msg = f"📚 {subject}\n\nПолезные ресурсы:\n\n"
    for title, url in links:
        msg += f"• {title}\n  {url}\n\n"
    msg += "Изучи материал и возвращайся за оценками! 💪"
    send_msg(user_id, msg, study_menu_kb())


# ============================================================
#  ОБРАБОТЧИКИ — МОТИВАЦИЯ, СОВЕТЫ, ПОМОЩЬ
# ============================================================

def handle_motivation(user_id):
    data = get_user_data(user_id)
    today = datetime.now().strftime("%Y-%m-%d")

    if data["last_quote_date"] == today:
        name, story = random.choice(MOTIVATION_STORIES)
        msg = f"🌟 История вдохновения\n\n{name}\n\n{story}\n\n💪 Не сдавайся!"
    else:
        quote = random.choice(MORNING_QUOTES)
        data["last_quote_date"] = today
        msg = f"⭐ Мотивация дня\n\n{quote}"

    send_msg(user_id, msg, main_menu_kb())


def handle_tip(user_id):
    tip = random.choice(STUDY_TIPS)
    send_msg(user_id, tip, main_menu_kb())


def handle_help(user_id):
    msg = (
        f"ℹ️ {BOT_NAME} v{VERSION}\n\n"
        "Я помогаю школьнику в учёбе:\n\n"
        "📅 Расписание — добавляй и смотри уроки по дням недели\n"
        "📝 Домашка — записывай задания и не забывай\n"
        "⏰ Напоминания — не пропусти важное\n"
        "🏆 Оценки — следи за успеваемостью и средним баллом\n"
        "📚 Учёба (ЦОК) — ссылки на полезные ресурсы\n"
        "🎯 Цели недели — ставь цели и отмечай выполнение\n"
        "⭐ Мотивация — вдохновение на каждый день\n"
        "💡 Совет дня — полезный совет по учёбе\n\n"
        "Нажми на кнопку меню, чтобы начать!"
    )
    send_msg(user_id, msg, main_menu_kb())


# ============================================================
#  ГЛАВНЫЙ ОБРАБОТЧИК
# ============================================================

def handle_message(event):
    user_id = event.user_id
    text = event.text.lower().strip()
    original_texts[user_id] = event.text

    state = get_state(user_id)

    # Если есть активное состояние — обрабатываем его
    if state:
        handled = handle_state(user_id, text, state)
        if handled:
            return

    # Обработка главного меню
    if handle_main_menu(user_id, text):
        return

    # Обработка подменю (если нет активного состояния)
    if handle_submenu(user_id, text):
        return

    # Если ничего не подошло
    send_msg(user_id,
             "Я не понял команду 🤔\n"
             "Нажми на кнопку в меню или напиши «Начать».",
             main_menu_kb())


def handle_submenu(user_id, text):
    """Обработка подменю без активного состояния."""
    if handle_schedule_menu(user_id, text):
        return True
    if handle_homework_menu(user_id, text):
        return True
    if handle_reminders_menu(user_id, text):
        return True
    if handle_grades_menu(user_id, text):
        return True
    if handle_goals_menu(user_id, text):
        return True
    if handle_study_menu(user_id, text):
        return True
    return False


def handle_state(user_id, text, state):
    """Маршрутизация по активным состояниям."""
    st = state["state"]

    handlers = {
        "schedule_day": handle_schedule_day,
        "schedule_subject": handle_schedule_subject,
        "schedule_delete_day": handle_schedule_delete_day,
        "hw_subject": handle_homework_subject,
        "hw_text": handle_homework_text,
        "hw_delete": handle_homework_delete,
        "reminder_text": handle_reminder_text,
        "reminder_delete": handle_reminder_delete,
        "grade_subject": handle_grade_subject,
        "grade_value": handle_grade_value,
        "grade_clear": handle_grade_clear,
        "goal_add": handle_goal_add,
        "goal_done": handle_goal_done,
        "goal_delete": handle_goal_delete,
    }

    handler = handlers.get(st)
    if handler:
        return handler(user_id, text)
    return False


# ============================================================
#  ИНИЦИАЛИЗАЦИЯ VK API
# ============================================================

try:
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
except vk_api.exceptions.ApiError as e:
    print(f"[VK API ERROR] Не удалось инициализировать: {e}")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Не удалось инициализировать: {e}")
    sys.exit(1)


# ============================================================
#  ОСНОВНОЙ ЦИКЛ
# ============================================================

print("=" * 60)
print(f"  {BOT_NAME} v{VERSION}")
print("  Бот запущен и готов к работе!")
print("=" * 60)

while True:
    try:
        for event in longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                try:
                    handle_message(event)
                except Exception as e:
                    print(f"[ERROR] Ошибка обработки сообщения: {e}")
                    user_id = event.user_id
                    try:
                        send_msg(user_id,
                                 "Произошла ошибка 😅 "
                                 "Попробуй ещё раз — напиши «Начать».",
                                 main_menu_kb())
                    except Exception:
                        pass
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем.")
        break
    except Exception as e:
        print(f"[CRITICAL] Ошибка в цикле: {e}")
        time.sleep(5)
        print("Переподключение...")
        continue
