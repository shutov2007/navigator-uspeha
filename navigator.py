#!/usr/bin/env python3
"""
Навигатор Успеха v1.0 — чат-бот для ВКонтакте.
Помогает школьнику организовать время, напоминает о событиях,
даёт ссылки на учебные материалы ЦОК, отслеживает оценки
и мотивирует на достижения.

Для конкурса «Технологии Первых» 2026.
Автор: [Святослав Шутов], г. Мамоново, Калининградская область.
"""

#!/usr/bin/env python3
import os
import random
import time
from datetime import datetime

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: Переменная окружения VK_TOKEN не найдена!")
    print("👉 Добавь её в панели Bothost: имя — VK_TOKEN, значение — токен сообщества.")
    exit(1)

print("✅ Токен загружен, бот запускается...")

# --- ДАННЫЕ (в памяти, без файла) ---
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
]

STUDY_TIPS = [
    "💡 Совет: читай учебник с карандашом — отмечай главное прямо в тексте.",
    "💡 Совет: объясни новую тему кому-то — так ты поймёшь её лучше.",
    "💡 Совет: делай домашку в тишине, без телефона рядом. 25 минут работы, 5 отдыха — техника Pomodoro.",
]

# Хранилище состояний (чтобы не спамить)
last_message_time = {}
MIN_INTERVAL_SECONDS = 2

# --- КЛАВИАТУРЫ ---
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
        [("⏰ Напоминания", VkKeyboardColor.PRIMARY),
         ("🏆 Оценки", VkKeyboardColor.POSITIVE)],
        [("📚 Учёба (ЦОК)", VkKeyboardColor.POSITIVE),
         ("🎯 Цели недели", VkKeyboardColor.POSITIVE)],
        [("⭐ Мотивация", VkKeyboardColor.SECONDARY),
         ("💡 Совет дня", VkKeyboardColor.SECONDARY)],
        [("ℹ️ Помощь", VkKeyboardColor.SECONDARY)],
    ])

def categories_keyboard():
    cats = list(SUBJECT_CATEGORIES.keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = []
        for cat in cats[i:i+2]:
            row.append((f"📁 {cat}", VkKeyboardColor.PRIMARY))
        rows.append(row)
    rows.append([("⬅️ Назад", VkKeyboardColor.SECONDARY)])
    return build_keyboard(rows)

def subjects_keyboard(category):
    subjects = SUBJECT_CATEGORIES.get(category, [])
    rows = []
    for i in range(0, len(subjects), 2):
        row = []
        for subj in subjects[i:i+2]:
            row.append((subj, VkKeyboardColor.POSITIVE))
        rows.append(row)
    rows.append([
        ("⬅️ К категориям", VkKeyboardColor.SECONDARY),
        ("🏠 Главное меню", VkKeyboardColor.SECONDARY),
    ])
    return build_keyboard(rows)

# --- ОТПРАВКА СООБЩЕНИЙ ---
def send_message(user_id, text, keyboard=None):
    # Защита от спама
    now = time.time()
    if user_id in last_message_time:
        elapsed = now - last_message_time[user_id]
        if elapsed < MIN_INTERVAL_SECONDS:
            # Просто игнорируем повторную отправку за короткий срок
            return
    last_message_time[user_id] = now

    try:
        vk.messages.send(
            user_id=user_id,
            message=text,
            keyboard=keyboard,
            random_id=random.randint(0, 2**31 - 1)
        )
        print(f"[OK] Сообщение отправлено пользователю {user_id}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить сообщение: {e}")

# --- ОБРАБОТКА СООБЩЕНИЙ ---
def handle_message(event):
    text = event.text.lower()
    user_id = event.user_id

    # Главное меню
    if text in ["начать", "меню", "🏠 главное меню", "/start"]:
        send_message(user_id, "Привет! Я «Навигатор Успеха». Чем помочь?", main_keyboard())
        return

    # Учёба → категории
    if text == "📚 учёба (цок)":
        send_message(user_id, "Выбери категорию предметов:", categories_keyboard())
        return

    # Обработка категорий (по названию)
    for cat in SUBJECT_CATEGORIES:
        if text.startswith(f"📁 {cat}".lower()):
            send_message(user_id, f"Предметы категории «{cat}»:", subjects_keyboard(cat))
            return

    # Возврат к категориям
    if text in ["⬅️ к категориям", "к категориям"]:
        send_message(user_id, "Выбери категорию:", categories_keyboard())
        return

    # Назад
    if text in ["⬅️ назад", "назад"]:
        send_message(user_id, "Главное меню:", main_keyboard())
        return

    # Мотивация
    if text == "⭐ мотивация":
        quote = random.choice(MORNING_QUOTES)
        send_message(user_id, quote, main_keyboard())
        return

    # Совет дня
    if text == "💡 совет дня":
        tip = random.choice(STUDY_TIPS)
        send_message(user_id, tip, main_keyboard())
        return

    # Помощь
    if text == "ℹ️ помощь":
        send_message(user_id, "Я помогаю школьнику: расписание, напоминания, учёба, мотивация. Напиши «Начать», чтобы увидеть кнопки.", main_keyboard())
        return

    # По умолчанию
    send_message(user_id, "Нажми на кнопку в меню — я всё покажу!", main_keyboard())

# --- ЗАПУСК ---
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

print("==================================================")
print("  Навигатор Успеха v2.0 (исправленный)")
print("  Бот запущен! ✅")
print("==================================================")

try:
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            handle_message(event)
except Exception as e:
    print(f"[CRITICAL] Ошибка в цикле longpoll: {e}")
