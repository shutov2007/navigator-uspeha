# -*- coding: utf-8 -*-
"""
Навигатор успеха — чат-бот для ВКонтакте
Команда «Адреналин», конкурс «Технологии Первых»
Возрастная группа: 11-12 лет

Возможности:
  - Расписание уроков (кнопочный ввод: день → время → предмет)
  - Кружки и секции (кнопочный ввод: день → время → название)
  - ИИ-тьютор на базе GigaChat (Сбер)
  - Управление ДЗ с умными напоминаниями
  - Пользовательские напоминания
  - Геймификация (XP, уровни, стрик)
  - Утренние/вечерние мотивационные рассылки
  - Анализ нагрузки дня
  - Поделиться расписанием с другом
  - Ссылки на образовательные ресурсы РФ
"""

import os
import json
import hashlib
import logging
import threading
import random
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  КОНФИГУРАЦИЯ
# ============================================================

VK_TOKEN = os.getenv("VK_TOKEN", "ТВОЙ_VK_TOKEN")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID", "ТВОЙ_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", "ТВОЙ_CLIENT_SECRET")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "dbname": os.getenv("DB_NAME", "navigator"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "ТВОЙ_ПАРОЛЬ"),
    "port": os.getenv("DB_PORT", "5432"),
}

REMINDER_HOUR = 19          # час напоминания о ДЗ (накануне дедлайна)
REMINDER_CHECK_MIN = 5       # как часто проверять напоминания (в минутах)
MORNING_HOUR = 7             # час утреннего сообщения
EVENING_HOUR = 21            # час вечернего сообщения
XP_PER_LEVEL = 100           # сколько XP нужно для нового уровня

LESSON_TIMES = [
    "08:30", "09:30", "10:25", "11:30",
    "12:35", "13:35", "14:30", "15:20", "16:05"
]

CLUB_TIMES = [
    "15:00", "15:30", "16:00", "16:30",
    "17:00", "17:30", "18:00", "18:30", "19:00", "19:30"
]

DAYS = {
    1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"
}

SUBJECTS = [
    "Математика", "Русский язык", "Литература", "Английский",
    "История", "Обществознание", "География", "Биология",
    "Физика", "Химия", "Информатика", "Технология",
    "Физкультура", "Музыка", "ИЗО", "ОБЖ",
    "Разговоры о важном", "Мои горизонты"
]
SPECIAL_SUBJECTS = {"Разговоры о важном", "Мои горизонты"}

STUDY_LINKS = {
    "ЦОК": "https://m.edsoo.ru",
    "Учи.ру": "https://uchi.ru",
    "Яндекс.Учебник": "https://education.yandex.ru",
    "Stepik": "https://stepik.org",
    "Skysmart": "https://skysmart.ru",
    "ФИПИ": "https://fipi.ru",
    "РЭШ": "https://resh.edu.ru",
}

MORNING_PHRASES = [
    "Сегодня отличный день, чтобы сделать чуть больше, чем вчера! 💪",
    "Ты справишься со всем, что запланировано — шаг за шагом. ✨",
    "Помни: даже маленькие шаги ведут к большим победам! 🚀",
    "Новый день — новые возможности. Поехали! 🌟",
    "Ты умнее и сильнее, чем думаешь. Верю в тебя! 🌈",
]

EVENING_PHRASES = [
    "Ты сегодня молодец — пора отдохнуть и набраться сил! 🌙",
    "День был насыщенным, ты справился. Завтра будет новый шанс. ✨",
    "Спокойной ночи! Пусть завтра всё получится ещё лучше. 💤",
    "Гордись тем, что сделал сегодня. А завтра — новый день! 🌟",
    "Отдыхай с чистой совестью — ты заслужил! 🌙",
]

ANTI_STRESS_PHRASES = [
    "Вижу, день плотный. Помни: можно сделать только самое важное, остальное — завтра. 😊",
    "Сегодня много уроков, но ты обязательно справишься. Дыши глубоко! 🧘",
    "Нагрузка высокая — не забывай делать паузы между делами. 💙",
]

BADGES = {
    "Планер дня": "Выполнил все ДЗ за день",
    "Супер-организатор": "Выполнил 3 ДЗ подряд без просрочки",
    "Стрик-мастер": "7 дней подряд без пропусков",
    "Знаток": "Правильно ответил на 5 вопросов ИИ-тьютора",
    "Новичок": "Зарегистрировался в боте",
    "Знаток": "Достиг 2 уровня",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ============================================================
#  БАЗА ДАННЫХ
# ============================================================

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Создаёт все таблицы, если их ещё нет."""
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    vk_id BIGINT PRIMARY KEY,
                    username TEXT,
                    class_grade INT CHECK (class_grade BETWEEN 5 AND 9),
                    timezone TEXT DEFAULT 'Europe/Moscow',
                    level INT DEFAULT 1,
                    xp INT DEFAULT 0,
                    streak_days INT DEFAULT 0,
                    last_streak_date DATE,
                    last_active TIMESTAMP,
                    correct_ai_answers INT DEFAULT 0,
                    state TEXT DEFAULT 'main',
                    state_data TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_schedule (
                    id SERIAL PRIMARY KEY,
                    vk_id BIGINT REFERENCES users(vk_id) ON DELETE CASCADE,
                    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
                    subject TEXT NOT NULL,
                    start_time TIME NOT NULL,
                    is_special BOOLEAN DEFAULT FALSE,
                    UNIQUE(vk_id, day_of_week, start_time)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS extracurriculars (
                    id SERIAL PRIMARY KEY,
                    vk_id BIGINT REFERENCES users(vk_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
                    start_time TIME NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS homework (
                    id SERIAL PRIMARY KEY,
                    vk_id BIGINT REFERENCES users(vk_id) ON DELETE CASCADE,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    due_date DATE NOT NULL,
                    is_done BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    vk_id BIGINT REFERENCES users(vk_id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    trigger_time TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gigachat_cache (
                    topic_hash TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hw_reminders_sent (
                    hw_id INT REFERENCES homework(id) ON DELETE CASCADE,
                    sent_date DATE NOT NULL,
                    PRIMARY KEY (hw_id, sent_date)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    vk_id BIGINT PRIMARY KEY,
                    correct_answer TEXT,
                    topic TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        conn.commit()
    logging.info("База данных инициализирована.")

# --- Пользователи ---

def get_user(vk_id: int) -> Optional[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE vk_id = %s", (vk_id,))
            return cur.fetchone()

def create_user(vk_id: int, username: str) -> Dict:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (vk_id, username, state) VALUES (%s, %s, 'main') RETURNING *",
                (vk_id, username)
            )
            conn.commit()
            return cur.fetchone()

def set_class(vk_id: int, class_grade: int):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET class_grade = %s WHERE vk_id = %s", (class_grade, vk_id))
            conn.commit()

def set_state(vk_id: int, state: str, state_data: str = None):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET state = %s, state_data = %s WHERE vk_id = %s",
                (state, state_data, vk_id)
            )
            conn.commit()

def update_last_active(vk_id: int):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_active = NOW() WHERE vk_id = %s", (vk_id,))
            conn.commit()

# --- Геймификация ---

def give_xp(vk_id: int, amount: int) -> Dict:
    """Начисляет XP и проверяет повышение уровня. Возвращает {'xp': total, 'level': lvl, 'leveled_up': bool}."""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT xp, level FROM users WHERE vk_id = %s", (vk_id,))
            u = cur.fetchone()
            if not u:
                return {"xp": 0, "level": 1, "leveled_up": False}
            new_xp = u["xp"] + amount
            new_level = new_xp // XP_PER_LEVEL + 1
            leveled_up = new_level > u["level"]
            cur.execute(
                "UPDATE users SET xp = %s, level = %s WHERE vk_id = %s",
                (new_xp, new_level, vk_id)
            )
            conn.commit()
            return {"xp": new_xp, "level": new_level, "leveled_up": leveled_up}

def update_streak(vk_id: int):
    today = date.today()
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT last_streak_date, streak_days FROM users WHERE vk_id = %s", (vk_id,))
            u = cur.fetchone()
            if not u:
                return
            if u["last_streak_date"] is None or u["last_streak_date"] < today:
                new_streak = (u["streak_days"] + 1) if u["last_streak_date"] == today - timedelta(days=1) else 1
                cur.execute(
                    "UPDATE users SET streak_days = %s, last_streak_date = %s WHERE vk_id = %s",
                    (new_streak, today, vk_id)
                )
                conn.commit()

def get_hw_stats(vk_id: int) -> Dict:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            week_ago = date.today() - timedelta(days=7)
            cur.execute(
                "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_done = TRUE) AS done FROM homework WHERE vk_id = %s AND created_at >= %s",
                (vk_id, week_ago)
            )
            row = cur.fetchone()
            total = row["total"] if row else 0
            done = row["done"] if row else 0
            pct = round(done / total * 100) if total > 0 else 0
            return {"total": total, "done": done, "pct": pct}

# --- Расписание (уроки) ---

def add_lesson(vk_id: int, day: int, subject: str, start_time: str):
    is_special = subject in SPECIAL_SUBJECTS
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_schedule (vk_id, day_of_week, subject, start_time, is_special) VALUES (%s, %s, %s, %s, %s)",
                (vk_id, day, subject, start_time, is_special)
            )
            conn.commit()

def get_user_schedule(vk_id: int, day_of_week: Optional[int] = None) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if day_of_week is not None:
                cur.execute(
                    "SELECT * FROM user_schedule WHERE vk_id = %s AND day_of_week = %s ORDER BY start_time",
                    (vk_id, day_of_week)
                )
            else:
                cur.execute(
                    "SELECT * FROM user_schedule WHERE vk_id = %s ORDER BY day_of_week, start_time",
                    (vk_id,)
                )
            return cur.fetchall()

def delete_lesson(vk_id: int, lesson_id: int) -> bool:
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_schedule WHERE vk_id = %s AND id = %s", (vk_id, lesson_id))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted

# --- Кружки ---

def add_club(vk_id: int, name: str, day: int, start_time: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extracurriculars (vk_id, name, day_of_week, start_time) VALUES (%s, %s, %s, %s)",
                (vk_id, name, day, start_time)
            )
            conn.commit()

def get_user_clubs(vk_id: int, day_of_week: Optional[int] = None) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if day_of_week is not None:
                cur.execute(
                    "SELECT * FROM extracurriculars WHERE vk_id = %s AND day_of_week = %s ORDER BY start_time",
                    (vk_id, day_of_week)
                )
            else:
                cur.execute(
                    "SELECT * FROM extracurriculars WHERE vk_id = %s ORDER BY day_of_week, start_time",
                    (vk_id,)
                )
            return cur.fetchall()

def delete_club(vk_id: int, club_id: int) -> bool:
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM extracurriculars WHERE vk_id = %s AND id = %s", (vk_id, club_id))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted

# --- ДЗ ---

def add_homework(vk_id: int, subject: str, description: str, due_date: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO homework (vk_id, subject, description, due_date) VALUES (%s, %s, %s, %s)",
                (vk_id, subject, description, due_date)
            )
            conn.commit()

def get_pending_hw(vk_id: int) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM homework WHERE vk_id = %s AND is_done = FALSE ORDER BY due_date",
                (vk_id,)
            )
            return cur.fetchall()

def mark_hw_done(vk_id: int, hw_id: int) -> bool:
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE homework SET is_done = TRUE WHERE vk_id = %s AND id = %s AND is_done = FALSE",
                (vk_id, hw_id)
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated

def get_hw_for_reminder(tomorrow: date) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT h.*, u.username, u.vk_id AS user_vk_id FROM homework h
                JOIN users u ON h.vk_id = u.vk_id
                WHERE h.is_done = FALSE AND h.due_date = %s
            """, (tomorrow,))
            return cur.fetchall()

def is_hw_reminder_sent(hw_id: int, sent_date: date) -> bool:
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM hw_reminders_sent WHERE hw_id = %s AND sent_date = %s",
                (hw_id, sent_date)
            )
            return cur.fetchone() is not None

def mark_hw_reminder_sent(hw_id: int, sent_date: date):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hw_reminders_sent (hw_id, sent_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (hw_id, sent_date)
            )
            conn.commit()

# --- Напоминания ---

def add_reminder(vk_id: int, text: str, trigger_time: datetime):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (vk_id, text, trigger_time) VALUES (%s, %s, %s)",
                (vk_id, text, trigger_time)
            )
            conn.commit()

def get_due_reminders(now: datetime) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE trigger_time <= %s AND is_active = TRUE",
                (now,)
            )
            return cur.fetchall()

def deactivate_reminder(reminder_id: int):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE reminders SET is_active = FALSE WHERE id = %s", (reminder_id,))
            conn.commit()

def get_active_reminders(vk_id: int) -> List[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE vk_id = %s AND is_active = TRUE ORDER BY trigger_time",
                (vk_id,)
            )
            return cur.fetchall()

def get_today_reminders(vk_id: int) -> List[Dict]:
    today = date.today()
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE vk_id = %s AND is_active = TRUE AND trigger_time::date = %s ORDER BY trigger_time",
                (vk_id, today)
            )
            return cur.fetchall()

def delete_reminder(vk_id: int, reminder_id: int) -> bool:
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reminders WHERE vk_id = %s AND id = %s", (vk_id, reminder_id))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted

def toggle_reminder(vk_id: int, reminder_id: int) -> Optional[bool]:
    """Переключает активность напоминания. Возвращает новое состояние или None."""
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT is_active FROM reminders WHERE vk_id = %s AND id = %s", (vk_id, reminder_id))
            row = cur.fetchone()
            if not row:
                return None
            new_state = not row["is_active"]
            cur.execute("UPDATE reminders SET is_active = %s WHERE id = %s", (new_state, reminder_id))
            conn.commit()
            return new_state

# --- Quiz sessions (для ИИ-тьютора) ---

def save_quiz_session(vk_id: int, correct_answer: str, topic: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quiz_sessions (vk_id, correct_answer, topic) VALUES (%s, %s, %s) "
                "ON CONFLICT (vk_id) DO UPDATE SET correct_answer = EXCLUDED.correct_answer, topic = EXCLUDED.topic, created_at = NOW()",
                (vk_id, correct_answer, topic)
            )
            conn.commit()

def get_quiz_session(vk_id: int) -> Optional[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM quiz_sessions WHERE vk_id = %s", (vk_id,))
            return cur.fetchone()

def clear_quiz_session(vk_id: int):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM quiz_sessions WHERE vk_id = %s", (vk_id,))
            conn.commit()

# ============================================================
#  GIGACHAT (Сбер)
# ============================================================

def get_gigachat_token() -> Optional[str]:
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": hashlib.uuid4().hex,
    }
    data = {
        "scope": GIGACHAT_SCOPE,
    }
    # GigaChat использует Basic auth с client_id:client_secret
    import base64
    auth_str = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    headers["Authorization"] = f"Basic {auth_b64}"

    try:
        resp = requests.post(url, headers=headers, data=data, verify=False, timeout=15)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        logging.error(f"GigaChat auth error: {e}")
        return None

def hash_topic(topic: str, class_grade: int) -> str:
    return hashlib.sha256(f"{topic}:{class_grade}".encode()).hexdigest()

def get_cached_gigachat(topic_hash: str) -> Optional[Dict]:
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT response_json FROM gigachat_cache WHERE topic_hash = %s", (topic_hash,))
            row = cur.fetchone()
            if row:
                return json.loads(row["response_json"])
    return None

def cache_gigachat(topic_hash: str, response: Dict):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gigachat_cache (topic_hash, response_json) VALUES (%s, %s) "
                "ON CONFLICT (topic_hash) DO UPDATE SET response_json = EXCLUDED.response_json",
                (topic_hash, json.dumps(response, ensure_ascii=False))
            )
            conn.commit()

def call_gigachat(topic: str, class_grade: int) -> Optional[Dict]:
    topic_hash = hash_topic(topic, class_grade)

    # Проверяем кэш
    cached = get_cached_gigachat(topic_hash)
    if cached:
        logging.info(f"GigaChat: ответ из кэша для темы '{topic}'")
        return cached

    token = get_gigachat_token()
    if not token:
        return None

    prompt = (
        f"Объясни тему \"{topic}\" для ученика {class_grade} класса простым и понятным языком, "
        "как будто ты добрый школьный учитель. Используй 2-3 примера из жизни (еда, игры, спорт, магазин). "
        "Текст объяснения должен быть не очень длинным — 4-6 абзацев. "
        "После объяснения задай 1 проверочный вопрос с 3 вариантами ответа (А, Б, В). "
        "Ответ верни СТРОГО в формате JSON:\n"
        '{"explanation": "текст объяснения", '
        '"question": "текст вопроса", '
        '"options": {"А": "вариант А", "Б": "вариант Б", "В": "вариант В"}, '
        '"correct": "А"}'
    )

    url = "https://gigachat.devices.sberbank.ru/api/v2/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model": "GigaChat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=45)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Очистка от markdown-обёртки
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        data = json.loads(content)
        cache_gigachat(topic_hash, data)
        logging.info(f"GigaChat: новый ответ для темы '{topic}' сохранён в кэш")
        return data
    except Exception as e:
        logging.error(f"GigaChat call error: {e}")
        return None

# ============================================================
#  VK КЛАВИАТУРЫ
# ============================================================

def kb_main_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("📅 Что сегодня?", color=VkKeyboardColor.PRIMARY)
    kb.add_button("📚 ИИ-тьютор", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("🎒 ДЗ", color=VkKeyboardColor.PRIMARY)
    kb.add_button("🔔 Напоминания", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("📊 Прогресс", color=VkKeyboardColor.SECONDARY)
    kb.add_button("🔗 Учёба", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("📋 Расписание", color=VkKeyboardColor.SECONDARY)
    kb.add_button("🎯 Кружки", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("🤝 Поделиться", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_back():
    kb = VkKeyboard(one_time=False)
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    return kb

def kb_back_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

def kb_days():
    kb = VkKeyboard(one_time=False)
    for day_num in [1, 2, 3, 4, 5]:
        kb.add_button(f"day_{day_num}", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("day_6", color=VkKeyboardColor.PRIMARY)
    kb.add_button("day_7", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    return kb

def kb_lesson_times():
    kb = VkKeyboard(one_time=False)
    for i, t in enumerate(LESSON_TIMES):
        kb.add_button(f"time_{t}", color=VkKeyboardColor.PRIMARY)
        if i % 3 == 2:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    return kb

def kb_club_times():
    kb = VkKeyboard(one_time=False)
    for i, t in enumerate(CLUB_TIMES):
        kb.add_button(f"ctime_{t}", color=VkKeyboardColor.PRIMARY)
        if i % 3 == 2:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    return kb

def kb_subjects():
    kb = VkKeyboard(one_time=False)
    for i, s in enumerate(SUBJECTS):
        color = VkKeyboardColor.POSITIVE if s in SPECIAL_SUBJECTS else VkKeyboardColor.SECONDARY
        kb.add_button(f"subj_{s}", color=color)
        if i % 2 == 1:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    return kb

def kb_schedule_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить урок", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("📋 Моё расписание", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("❌ Удалить урок", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

def kb_clubs_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить кружок", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("📋 Мои кружки", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("❌ Удалить кружок", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

def kb_hw_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить ДЗ", color=VkKeyboardColor.POSITIVE)
    kb.add_button("📋 Мои ДЗ", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

def kb_reminders_menu():
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить", color=VkKeyboardColor.POSITIVE)
    kb.add_button("📋 Сегодня", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("📋 Все", color=VkKeyboardColor.PRIMARY)
    kb.add_button("❌ Удалить", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🔄 Вкл/Выкл", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

def kb_quiz_options(options: Dict[str, str]):
    kb = VkKeyboard(one_time=True)
    for key in sorted(options.keys()):
        kb.add_button(f"quiz_{key}", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_study_links():
    kb = VkKeyboard(one_time=False)
    for name, url in STUDY_LINKS.items():
        kb.add_openlink_button(label=name, link=url)
        kb.add_line()
    kb.add_button("🏠 Меню", color=VkKeyboardColor.PRIMARY)
    return kb

# ============================================================
#  ОТПРАВКА СООБЩЕНИЙ
# ============================================================

_vk_session = None

def get_vk_api():
    global _vk_session
    if _vk_session is None:
        _vk_session = vk_api.VkApi(token=VK_TOKEN)
    return _vk_session.get_api()

def send_msg(vk_id: int, text: str, keyboard: VkKeyboard = None):
    vk = get_vk_api()
    try:
        vk.messages.send(
            peer_id=vk_id,
            message=text,
            keyboard=keyboard.get_keyboard() if keyboard else None,
            random_id=random.randint(0, 2**31)
        )
    except Exception as e:
        logging.error(f"Send message failed: {e}")

def send_typing(vk_id: int):
    vk = get_vk_api()
    try:
        vk.messages.setActivity(peer_id=vk_id, type="typing")
    except:
        pass

# ============================================================
#  ФОРМИРОВАНИЕ ТЕКСТОВ
# ============================================================

def format_load_emoji(load: int) -> str:
    if load <= 3:
        return "😴😴😴" + " ⬜" * 7
    elif load <= 6:
        return "😐😐😐😐😐😐" + " ⬜" * 4
    else:
        return "😵" * min(load, 10)

def format_schedule_text(lessons: List[Dict], clubs: List[Dict]) -> str:
    text = ""
    if lessons:
        text += "📚 Уроки:\n"
        for l in lessons:
            special = " 🟢" if l["is_special"] else ""
            t = l["start_time"].strftime("%H:%M") if hasattr(l["start_time"], "strftime") else str(l["start_time"])
            text += f"  ⏰ {t} — {l['subject']}{special}\n"
    else:
        text += "📚 Уроков нет\n"
    if clubs:
        text += "\n🎯 Кружки:\n"
        for c in clubs:
            t = c["start_time"].strftime("%H:%M") if hasattr(c["start_time"], "strftime") else str(c["start_time"])
            text += f"  ⏰ {t} — {c['name']}\n"
    return text if text else "Сегодня свободный день! 🎉"

def format_full_schedule(vk_id: int) -> str:
    text = "📋 Расписание на неделю:\n\n"
    for day_num in range(1, 8):
        lessons = get_user_schedule(vk_id, day_num)
        clubs = get_user_clubs(vk_id, day_num)
        if not lessons and not clubs:
            continue
        text += f"📅 {DAYS[day_num]}:\n"
        for l in lessons:
            t = l["start_time"].strftime("%H:%M") if hasattr(l["start_time"], "strftime") else str(l["start_time"])
            special = " 🟢" if l["is_special"] else ""
            text += f"  ⏰ {t} — {l['subject']}{special}\n"
        for c in clubs:
            t = c["start_time"].strftime("%H:%M") if hasattr(c["start_time"], "strftime") else str(c["start_time"])
            text += f"  🎯 {t} — {c['name']}\n"
        text += "\n"
    if text == "📋 Расписание на неделю:\n\n":
        text = "Твоё расписание пока пустое. Добавь уроки в разделе «📋 Расписание»! 📝"
    return text

def format_full_clubs(vk_id: int) -> str:
    clubs = get_user_clubs(vk_id)
    if not clubs:
        return "У тебя пока нет кружков. Добавь в разделе «🎯 Кружки»! 🎯"
    text = "🎯 Твои кружки:\n\n"
    for c in clubs:
        t = c["start_time"].strftime("%H:%M") if hasattr(c["start_time"], "strftime") else str(c["start_time"])
        text += f"🆔 {c['id']} | {DAYS[c['day_of_week']]} {t} — {c['name']}\n"
    return text

def format_progress(vk_id: int) -> str:
    u = get_user(vk_id)
    stats = get_hw_stats(vk_id)
    xp_in_level = u["xp"] % XP_PER_LEVEL
    text = (
        f"📊 Твой прогресс:\n\n"
        f"🏆 Уровень: {u['level']}\n"
        f"⭐ XP: {u['xp']} (до следующего уровня: {XP_PER_LEVEL - xp_in_level})\n"
        f"🔥 Стрик: {u['streak_days']} дн. подряд\n"
        f"✅ ДЗ за неделю: {stats['done']}/{stats['total']} ({stats['pct']}%)\n"
        f"🧠 Правильных ответов ИИ-тьютора: {u.get('correct_ai_answers', 0)}\n"
    )
    if u["level"] >= 2:
        text += f"\n🏅 Значок: «Знаток» (2 уровень)"
    if u["streak_days"] >= 7:
        text += f"\n🏅 Значок: «Стрик-мастер» (7 дней подряд)"
    return text

# ============================================================
#  ФОНОВЫЕ ЗАДАЧИ (APScheduler)
# ============================================================

scheduler = BlockingScheduler()

def morning_motivation():
    logging.info("Запуск утренней рассылки...")
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE class_grade IS NOT NULL")
            users = cur.fetchall()
    for u in users:
        try:
            today = datetime.now().weekday() + 1
            lessons = get_user_schedule(u["vk_id"], today)
            clubs = get_user_clubs(u["vk_id"], today)
            load = len(lessons) + len(clubs)
            name = u["username"] or "друг"
            motivation = random.choice(MORNING_PHRASES)
            text = (
                f"Доброе утро, {name}! 🌞\n\n"
                f"Сегодня у тебя {len(lessons)} уроков и {len(clubs)} кружков.\n"
                f"Нагрузка: {format_load_emoji(load)}\n\n"
            )
            if load >= 7:
                text += random.choice(ANTI_STRESS_PHRASES) + "\n\n"
            text += f"{motivation}\n\n"
            text += "План на день — в разделе «📅 Что сегодня?». Удачи! 🍀"
            send_msg(u["vk_id"], text)
        except Exception as e:
            logging.error(f"Morning message failed for {u['vk_id']}: {e}")

def evening_motivation():
    logging.info("Запуск вечерней рассылки...")
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE class_grade IS NOT NULL")
            users = cur.fetchall()
    for u in users:
        try:
            pending = get_pending_hw(u["vk_id"])
            name = u["username"] or "друг"
            motivation = random.choice(EVENING_PHRASES)
            text = (
                f"Спокойной ночи, {name}! 🌙\n\n"
                f"У тебя осталось {len(pending)} невыполненных ДЗ. "
            )
            if pending:
                text += "Не переживай — завтра разберёшься! 💪\n\n"
            else:
                text += "Ты всё сделал — красавчик! 🌟\n\n"
            text += f"{motivation}\n\nЯ буду здесь утром. До встречи! 👋"
            send_msg(u["vk_id"], text)
        except Exception as e:
            logging.error(f"Evening message failed for {u['vk_id']}: {e}")

def check_reminders_and_hw():
    now = datetime.now()
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Пользовательские напоминания
            cur.execute("SELECT * FROM reminders WHERE trigger_time <= %s AND is_active = TRUE", (now,))
            reminders = cur.fetchall()
    for r in reminders:
        try:
            send_msg(r["vk_id"], f"⏰ Напоминание: {r['text']}")
            deactivate_reminder(r["id"])
        except Exception as e:
            logging.error(f"Reminder send failed: {e}")

    # Умные напоминания о ДЗ — каждый час после REMINDER_HOUR
    if now.hour >= REMINDER_HOUR:
        tomorrow = now.date() + timedelta(days=1)
        hw_list = get_hw_for_reminder(tomorrow)
        for hw in hw_list:
            if is_hw_reminder_sent(hw["id"], now.date()):
                continue
            try:
                text = (
                    f"⏰ Внимание!\n\n"
                    f"Завтра дедлайн по ДЗ:\n"
                    f"📘 {hw['subject']}\n"
                    f"📝 {hw['description']}\n"
                    f"🗓 Срок: {hw['due_date']}\n\n"
                    f"Не забудь выполнить сегодня вечером! Ты сможешь! 💪"
                )
                send_msg(hw["user_vk_id"], text)
                mark_hw_reminder_sent(hw["id"], now.date())
            except Exception as e:
                logging.error(f"HW reminder failed: {e}")

def setup_scheduler():
    scheduler.add_job(morning_motivation, CronTrigger(hour=MORNING_HOUR, minute=0))
    scheduler.add_job(evening_motivation, CronTrigger(hour=EVENING_HOUR, minute=0))
    scheduler.add_job(check_reminders_and_hw, "interval", minutes=REMINDER_CHECK_MIN)

# ============================================================
#  ГЛАВНЫЙ ЦИКЛ
# ============================================================

def handle_message(event, vk):
    user_id = event.user_id
    raw_text = event.text or ""
    text = raw_text.strip().lower()
    user = get_user(user_id)
    update_last_active(user_id)

    # --- Если пользователя нет — создаём ---
    if not user:
        user = create_user(user_id, event.user_name if hasattr(event, 'user_name') else None)
        give_xp(user_id, 10)  # значок «Новичок»
        send_msg(user_id,
            "Привет! 👋 Я «Навигатор успеха» — твой помощник в учёбе.\n\n"
            "Я помогу с расписанием, ДЗ, объясню сложные темы и не дам ничего забыть!\n\n"
            "В каком ты классе (5–9)? Напиши просто цифру."
        )
        return

    # --- Если класс не выбран ---
    if user["class_grade"] is None:
        if text.isdigit() and 5 <= int(text) <= 9:
            set_class(user_id, int(text))
            send_msg(user_id,
                f"Отлично! Теперь я подстрою объяснения под {text} класс. 🎯\n\n"
                "Выбери, что хочешь сделать:",
                keyboard=kb_main_menu()
            )
        else:
            send_msg(user_id, "Напиши цифру от 5 до 9 — в каком ты классе? 😊")
        return

    state = user.get("state", "main")
    state_data = user.get("state_data")

    # --- Кнопка "Назад" ---
    if text == "🔙 назад":
        set_state(user_id, "main")
        send_msg(user_id, "Возвращаемся в меню! 🏠", keyboard=kb_main_menu())
        return

    # --- Кнопка "Меню" ---
    if text == "🏠 меню":
        set_state(user_id, "main")
        clear_quiz_session(user_id)
        send_msg(user_id, "Главное меню! Выбирай: 👇", keyboard=kb_main_menu())
        return

    # --- Кнопка "/start" ---
    if text == "/start" or text == "начать":
        set_state(user_id, "main")
        send_msg(user_id, "Главное меню! Выбирай: 👇", keyboard=kb_main_menu())
        return

    # ============================================================
    #  РАЗДЕЛ: ЧТО СЕГОДНЯ?
    # ============================================================
    if text == "📅 что сегодня?":
        today = datetime.now().weekday() + 1
        lessons = get_user_schedule(user_id, today)
        clubs = get_user_clubs(user_id, today)
        load = len(lessons) + len(clubs)
        text_resp = f"📅 План на сегодня ({DAYS.get(today, '?')}):\n\n"
        text_resp += format_schedule_text(lessons, clubs)
        text_resp += f"\n📊 Нагрузка: {format_load_emoji(load)}\n"
        if load >= 7:
            text_resp += "\n" + random.choice(ANTI_STRESS_PHRASES)
        send_msg(user_id, text_resp, keyboard=kb_main_menu())
        return

    # ============================================================
    #  РАЗДЕЛ: РАСПИСАНИЕ (кнопочный ввод)
    # ============================================================
    if text == "📋 расписание":
        set_state(user_id, "schedule_menu")
        send_msg(user_id, "📋 Управление расписанием:\n\nДобавляй уроки кнопками — день → время → предмет.",
                 keyboard=kb_schedule_menu())
        return

    if state == "schedule_menu":
        if text == "➕ добавить урок":
            set_state(user_id, "schedule_day", "")
            send_msg(user_id, "Выбери день недели:", keyboard=kb_days())
            return

        if text == "📋 моё расписание":
            send_msg(user_id, format_full_schedule(user_id), keyboard=kb_schedule_menu())
            return

        if text == "❌ удалить урок":
            lessons_all = get_user_schedule(user_id)
            if not lessons_all:
                send_msg(user_id, "Уроков пока нет — нечего удалять. 🤷", keyboard=kb_schedule_menu())
                return
            text_resp = "Список уроков (отправь ID для удаления):\n\n"
            for l in lessons_all:
                t = l["start_time"].strftime("%H:%M") if hasattr(l["start_time"], "strftime") else str(l["start_time"])
                text_resp += f"🆔 {l['id']} | {DAYS[l['day_of_week']]} {t} — {l['subject']}\n"
            set_state(user_id, "schedule_delete", "")
            send_msg(user_id, text_resp, keyboard=kb_back_menu())
            return

    # --- Выбор дня для расписания ---
    if state == "schedule_day" and text.startswith("day_"):
        day_num = int(text.split("_")[1])
        set_state(user_id, "schedule_time", str(day_num))
        send_msg(user_id, f"День: {DAYS[day_num]}\nВыбери время урока:", keyboard=kb_lesson_times())
        return

    # --- Выбор времени для расписания ---
    if state == "schedule_time" and text.startswith("time_"):
        chosen_time = text.split("_", 1)[1]
        day_num = int(state_data)
        set_state(user_id, "schedule_subject", f"{day_num}|{chosen_time}")
        send_msg(user_id, f"День: {DAYS[day_num]}, время: {chosen_time}\nВыбери предмет:", keyboard=kb_subjects())
        return

    # --- Выбор предмета ---
    if state == "schedule_subject" and text.startswith("subj_"):
        subject = text.split("_", 1)[1]
        parts = state_data.split("|")
        day_num = int(parts[0])
        chosen_time = parts[1]
        try:
            add_lesson(user_id, day_num, subject, chosen_time)
            result = give_xp(user_id, 10)
            resp = f"✅ Урок добавлен!\n📚 {DAYS[day_num]} {chosen_time} — {subject}\n+10 XP! 🎉"
            if result["leveled_up"]:
                resp += f"\n\n🏆 Поздравляю! Ты достиг {result['level']} уровня!"
            set_state(user_id, "schedule_menu")
            send_msg(user_id, resp, keyboard=kb_schedule_menu())
        except psycopg2.errors.UniqueViolation:
            set_state(user_id, "schedule_menu")
            send_msg(user_id, "❌ На это время уже есть урок! Выбери другое.", keyboard=kb_schedule_menu())
        return

    # --- Удаление урока ---
    if state == "schedule_delete" and text.isdigit():
        lesson_id = int(text)
        if delete_lesson(user_id, lesson_id):
            send_msg(user_id, f"✅ Урок с ID {lesson_id} удалён!", keyboard=kb_schedule_menu())
        else:
            send_msg(user_id, "❌ Не найден урок с таким ID.", keyboard=kb_schedule_menu())
        set_state(user_id, "schedule_menu")
        return

    # ============================================================
    #  РАЗДЕЛ: КРУЖКИ (кнопочный ввод)
    # ============================================================
    if text == "🎯 кружки":
        set_state(user_id, "clubs_menu")
        send_msg(user_id, "🎯 Управление кружками:\n\nДобавляй кружки кнопками — день → время → название.",
                 keyboard=kb_clubs_menu())
        return

    if state == "clubs_menu":
        if text == "➕ добавить кружок":
            set_state(user_id, "club_day", "")
            send_msg(user_id, "Выбери день недели для кружка:", keyboard=kb_days())
            return

        if text == "📋 мои кружки":
            send_msg(user_id, format_full_clubs(user_id), keyboard=kb_clubs_menu())
            return

        if text == "❌ удалить кружок":
            clubs_all = get_user_clubs(user_id)
            if not clubs_all:
                send_msg(user_id, "Кружков пока нет — нечего удалять. 🤷", keyboard=kb_clubs_menu())
                return
            text_resp = "Список кружков (отправь ID для удаления):\n\n"
            for c in clubs_all:
                t = c["start_time"].strftime("%H:%M") if hasattr(c["start_time"], "strftime") else str(c["start_time"])
                text_resp += f"🆔 {c['id']} | {DAYS[c['day_of_week']]} {t} — {c['name']}\n"
            set_state(user_id, "club_delete", "")
            send_msg(user_id, text_resp, keyboard=kb_back_menu())
            return

    # --- Выбор дня для кружка ---
    if state == "club_day" and text.startswith("day_"):
        day_num = int(text.split("_")[1])
        set_state(user_id, "club_time", str(day_num))
        send_msg(user_id, f"День: {DAYS[day_num]}\nВыбери время кружка:", keyboard=kb_club_times())
        return

    # --- Выбор времени для кружка ---
    if state == "club_time" and text.startswith("ctime_"):
        chosen_time = text.split("_", 1)[1]
        day_num = int(state_data)
        set_state(user_id, "club_name", f"{day_num}|{chosen_time}")
        send_msg(user_id,
            f"День: {DAYS[day_num]}, время: {chosen_time}\n"
            "Напиши название кружка (например, «Футбол»):",
            keyboard=kb_back()
        )
        return

    # --- Ввод названия кружка ---
    if state == "club_name" and not text.startswith(("🔙", "🏠", "day_", "time_", "ctime_", "subj_", "quiz_")):
        parts = state_data.split("|")
        day_num = int(parts[0])
        chosen_time = parts[1]
        club_name = raw_text.strip()
        if len(club_name) < 2:
            send_msg(user_id, "Название слишком короткое. Попробуй ещё раз:")
            return
        add_club(user_id, club_name, day_num, chosen_time)
        result = give_xp(user_id, 10)
        resp = f"✅ Кружок добавлен!\n🎯 {DAYS[day_num]} {chosen_time} — {club_name}\n+10 XP! 🎉"
        if result["leveled_up"]:
            resp += f"\n\n🏆 Поздравляю! Ты достиг {result['level']} уровня!"
        set_state(user_id, "clubs_menu")
        send_msg(user_id, resp, keyboard=kb_clubs_menu())
        return

    # --- Удаление кружка ---
    if state == "club_delete" and text.isdigit():
        club_id = int(text)
        if delete_club(user_id, club_id):
            send_msg(user_id, f"✅ Кружок с ID {club_id} удалён!", keyboard=kb_clubs_menu())
        else:
            send_msg(user_id, "❌ Не найден кружок с таким ID.", keyboard=kb_clubs_menu())
        set_state(user_id, "clubs_menu")
        return

    # ============================================================
    #  РАЗДЕЛ: ИИ-ТЬЮТОР (GigaChat)
    # ============================================================
    if text == "📚 ии-тьютор":
        set_state(user_id, "ai_tutor", "")
        send_msg(user_id,
            "🧠 Напиши тему, которую не понял (например, «дроби», «Past Simple», «фотосинтез»).\n"
            "Я объясню простыми словами и задам проверочный вопрос!"
        )
        return

    if state == "ai_tutor" and not text.startswith(("🔙", "🏠", "day_", "time_", "ctime_", "subj_", "quiz_", "📋", "🎒", "🔔", "📊", "🔗", "🎯", "🤝", "📅", "➕", "❌", "🔄", "📋")):
        topic = raw_text.strip()
        if len(topic) < 2:
            send_msg(user_id, "Тема слишком короткая. Попробуй ещё раз:")
            return
        send_typing(user_id)
        send_msg(user_id, "Думаю над объяснением… 🧠")
        response = call_gigachat(topic, user["class_grade"])
        if response:
            explanation = response.get("explanation", "")
            question = response.get("question", "")
            options = response.get("options", {})
            correct = response.get("correct", "")
            text_resp = f"📝 Тема: «{topic}»\n\n{explanation}\n\n"
            text_resp += f"❓ Проверочный вопрос:\n{question}\n\n"
            if options:
                for key in sorted(options.keys()):
                    text_resp += f"  {key}) {options[key]}\n"
                save_quiz_session(user_id, correct, topic)
                send_msg(user_id, text_resp, keyboard=kb_quiz_options(options))
            else:
                text_resp += "\n(Варианты ответа не сгенерированы. Попробуй другую тему!)"
                send_msg(user_id, text_resp, keyboard=kb_main_menu())
        else:
            send_msg(user_id,
                "Прости, не получилось подключиться к ИИ. 😞\n"
                "Загляни в раздел «🔗 Учёба» — там есть ссылки на видеоуроки и материалы!",
                keyboard=kb_main_menu()
            )
        set_state(user_id, "main")
        return

    # --- Проверка ответа квиза ---
    if text.startswith("quiz_"):
        answer = text.split("_", 1)[1]
        session = get_quiz_session(user_id)
        if session:
            correct = session["correct_answer"]
            topic = session["topic"]
            if answer == correct:
                result = give_xp(user_id, 30)
                resp = f"✅ Правильно! Молодец! 🎉\n+30 XP!"
                # Увеличиваем счётчик правильных ответов
                with get_db_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE users SET correct_ai_answers = correct_ai_answers + 1 WHERE vk_id = %s", (user_id,))
                        conn.commit()
                if result["leveled_up"]:
                    resp += f"\n\n🏆 Ты достиг {result['level']} уровня!"
                u = get_user(user_id)
                if u.get("correct_ai_answers", 0) >= 5:
                    resp += "\n\n🏅 Значок: «Знаток» (5 правильных ответов)!"
            else:
                resp = f"❌ Почти! Правильный ответ: {correct}.\n\nНе переживай — ошибки помогают учиться! 💪\nМожешь попробовать другую тему в «📚 ИИ-тьютор»."
            clear_quiz_session(user_id)
            send_msg(user_id, resp, keyboard=kb_main_menu())
        else:
            send_msg(user_id, "Сессия истекла. Попробуй задать тему заново в «📚 ИИ-тьютор».", keyboard=kb_main_menu())
        return

    # ============================================================
    #  РАЗДЕЛ: ДЗ
    # ============================================================
    if text == "🎒 дз":
        set_state(user_id, "hw_menu")
        send_msg(user_id,
            "🎒 Управление ДЗ:\n\n"
            "• «➕ Добавить ДЗ» — добавь задание (предмет | описание | дата ГГГГ-ММ-ДД)\n"
            "• «📋 Мои ДЗ» — список невыполненных\n"
            "• Чтобы отметить выполненным, отправь ID из списка.",
            keyboard=kb_hw_menu()
        )
        return

    if state == "hw_menu":
        if text == "➕ добавить дз":
            set_state(user_id, "hw_add", "")
            send_msg(user_id,
                "Отправь в одном сообщении:\n"
                "Предмет | Описание | Дата (ГГГГ-ММ-ДД)\n\n"
                "Пример: Математика | Упр. 12, стр. 45 | 2024-10-25",
                keyboard=kb_back_menu()
            )
            return

        if text == "📋 мои дз":
            hw_list = get_pending_hw(user_id)
            if not hw_list:
                send_msg(user_id, "🎉 Нет невыполненных ДЗ! Ты молодец! 🌟", keyboard=kb_hw_menu())
            else:
                text_resp = "📋 Невыполненные ДЗ:\n\n"
                for hw in hw_list:
                    due = hw["due_date"].strftime("%d.%m.%Y") if hasattr(hw["due_date"], "strftime") else str(hw["due_date"])
                    text_resp += f"🆔 {hw['id']} | 📘 {hw['subject']}\n📝 {hw['description']}\n🗓 До: {due}\n\n"
                text_resp += "Отправь ID, чтобы отметить как выполненное."
                send_msg(user_id, text_resp, keyboard=kb_hw_menu())
            return

    if state == "hw_add" and "|" in raw_text:
        parts = [p.strip() for p in raw_text.split("|")]
        if len(parts) == 3:
            subject, description, due_date = parts
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
                add_homework(user_id, subject, description, due_date)
                result = give_xp(user_id, 10)
                resp = f"✅ ДЗ добавлено!\n📘 {subject} — {description}\n🗓 До: {due_date}\n+10 XP! 🎉"
                if result["leveled_up"]:
                    resp += f"\n\n🏆 Ты достиг {result['level']} уровня!"
                set_state(user_id, "hw_menu")
                send_msg(user_id, resp, keyboard=kb_hw_menu())
            except ValueError:
                send_msg(user_id, "❌ Неверный формат даты. Используй ГГГГ-ММ-ДД (например, 2024-10-25).")
            return

    # Отметка ДЗ выполненным (по ID)
    if state == "hw_menu" and text.isdigit():
        hw_id = int(text)
        if mark_hw_done(user_id, hw_id):
            result = give_xp(user_id, 20)
            update_streak(user_id)
            resp = f"✅ ДЗ с ID {hw_id} отмечено выполненным!\n+20 XP! 🎉"
            if result["leveled_up"]:
                resp += f"\n\n🏆 Ты достиг {result['level']} уровня!"
            send_msg(user_id, resp, keyboard=kb_hw_menu())
        else:
            send_msg(user_id, "❌ Не найдено ДЗ с таким ID. Проверь список «📋 Мои ДЗ».", keyboard=kb_hw_menu())
        return

    # ============================================================
    #  РАЗДЕЛ: НАПОМИНАНИЯ
    # ============================================================
    if text == "🔔 напоминания":
        set_state(user_id, "reminders_menu")
        send_msg(user_id,
            "🔔 Напоминания:\n\n"
            "• «➕ Добавить» — текст | дата и время (ГГГГ-ММ-ДД ЧЧ:ММ)\n"
            "• «📋 Сегодня» — напоминания на сегодня\n"
            "• «📋 Все» — все активные\n"
            "• «❌ Удалить» — отправь ID\n"
            "• «🔄 Вкл/Выкл» — переключить активность",
            keyboard=kb_reminders_menu()
        )
        return

    if state == "reminders_menu":
        if text == "➕ добавить":
            set_state(user_id, "reminder_add", "")
            send_msg(user_id,
                "Отправь: Текст | ГГГГ-ММ-ДД ЧЧ:ММ\n"
                "Пример: Купить тетрадь | 2024-10-25 15:00",
                keyboard=kb_back_menu()
            )
            return

        if text == "📋 сегодня":
            rems = get_today_reminders(user_id)
            if not rems:
                send_msg(user_id, "На сегодня нет напоминаний. 🎉", keyboard=kb_reminders_menu())
            else:
                text_resp = "🔔 Напоминания на сегодня:\n\n"
                for r in rems:
                    t = r["trigger_time"].strftime("%H:%M") if hasattr(r["trigger_time"], "strftime") else str(r["trigger_time"])
                    text_resp += f"🆔 {r['id']} | ⏰ {t} | {'✅' if r['is_active'] else '⏸'} {r['text']}\n"
                send_msg(user_id, text_resp, keyboard=kb_reminders_menu())
            return

        if text == "📋 все":
            rems = get_active_reminders(user_id)
            if not rems:
                send_msg(user_id, "Нет активных напоминаний. 🎉", keyboard=kb_reminders_menu())
            else:
                text_resp = "🔔 Все напоминания:\n\n"
                for r in rems:
                    t = r["trigger_time"].strftime("%d.%m %H:%M") if hasattr(r["trigger_time"], "strftime") else str(r["trigger_time"])
                    text_resp += f"🆔 {r['id']} | ⏰ {t} | {'✅' if r['is_active'] else '⏸'} {r['text']}\n"
                send_msg(user_id, text_resp, keyboard=kb_reminders_menu())
            return

        if text == "❌ удалить":
            rems = get_active_reminders(user_id)
            if not rems:
                send_msg(user_id, "Нечего удалять. 🤷", keyboard=kb_reminders_menu())
            else:
                text_resp = "Отправь ID напоминания для удаления:\n\n"
                for r in rems:
                    t = r["trigger_time"].strftime("%d.%m %H:%M") if hasattr(r["trigger_time"], "strftime") else str(r["trigger_time"])
                    text_resp += f"🆔 {r['id']} | {t} | {r['text']}\n"
                set_state(user_id, "reminder_delete", "")
                send_msg(user_id, text_resp, keyboard=kb_back_menu())
            return

        if text == "🔄 вкл/выкл":
            rems = get_active_reminders(user_id)
            inactive_rems = []
            with get_db_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM reminders WHERE vk_id = %s AND is_active = FALSE ORDER BY trigger_time", (user_id,))
                    inactive_rems = cur.fetchall()
            all_rems = rems + inactive_rems
            if not all_rems:
                send_msg(user_id, "Нет напоминаний для переключения. 🤷", keyboard=kb_reminders_menu())
            else:
                text_resp = "Отправь ID напоминания для вкл/выкл:\n\n"
                for r in all_rems:
                    t = r["trigger_time"].strftime("%d.%m %H:%M") if hasattr(r["trigger_time"], "strftime") else str(r["trigger_time"])
                    status = "✅ вкл" if r["is_active"] else "⏸ выкл"
                    text_resp += f"🆔 {r['id']} | {status} | {t} | {r['text']}\n"
                set_state(user_id, "reminder_toggle", "")
                send_msg(user_id, text_resp, keyboard=kb_back_menu())
            return

    if state == "reminder_add" and "|" in raw_text:
        parts = [p.strip() for p in raw_text.split("|")]
        if len(parts) == 2:
            rem_text, rem_time_str = parts
            try:
                trigger_time = datetime.strptime(rem_time_str, "%Y-%m-%d %H:%M")
                add_reminder(user_id, rem_text, trigger_time)
                set_state(user_id, "reminders_menu")
                send_msg(user_id,
                    f"✅ Напоминание добавлено!\n🔔 «{rem_text}» на {rem_time_str}",
                    keyboard=kb_reminders_menu()
                )
            except ValueError:
                send_msg(user_id, "❌ Неверный формат. Пример: Текст | 2024-10-25 15:00")
            return

    if state == "reminder_delete" and text.isdigit():
        rem_id = int(text)
        if delete_reminder(user_id, rem_id):
            send_msg(user_id, f"✅ Напоминание с ID {rem_id} удалено!", keyboard=kb_reminders_menu())
        else:
            send_msg(user_id, "❌ Не найдено напоминание с таким ID.", keyboard=kb_reminders_menu())
        set_state(user_id, "reminders_menu")
        return

    if state == "reminder_toggle" and text.isdigit():
        rem_id = int(text)
        new_state_rem = toggle_reminder(user_id, rem_id)
        if new_state_rem is not None:
            status = "✅ включено" if new_state_rem else "⏸ выключено"
            send_msg(user_id, f"Напоминание с ID {rem_id} {status}!", keyboard=kb_reminders_menu())
        else:
            send_msg(user_id, "❌ Не найдено напоминание с таким ID.", keyboard=kb_reminders_menu())
        set_state(user_id, "reminders_menu")
        return

    # ============================================================
    #  РАЗДЕЛ: ПРОГРЕСС
    # ============================================================
    if text == "📊 прогресс":
        send_msg(user_id, format_progress(user_id), keyboard=kb_main_menu())
        return

    # ============================================================
    #  РАЗДЕЛ: УЧЁБА (ССЫЛКИ)
    # ============================================================
    if text == "🔗 учёба":
        links_text = "🔗 Полезные образовательные ресурсы:\n\n"
        for name, url in STUDY_LINKS.items():
            links_text += f"• {name}: {url}\n"
        links_text += "\nНажимай на кнопки — откроются сайты! 📚"
        send_msg(user_id, links_text, keyboard=kb_study_links())
        return

    # ============================================================
    #  РАЗДЕЛ: ПОДЕЛИТЬСЯ
    # ============================================================
    if text == "🤝 поделиться":
        today = datetime.now().weekday() + 1
        lessons = get_user_schedule(user_id, today)
        clubs = get_user_clubs(user_id, today)
        share_text = f"📅 Моё расписание на {DAYS.get(today, 'сегодня')}:\n\n"
        share_text += format_schedule_text(lessons, clubs)
        share_text += "\nСкопируй и отправь другу! 🤝"
        send_msg(user_id, share_text, keyboard=kb_main_menu())
        return

    # ============================================================
    #  Fallback — если ничего не распознано
    # ============================================================
    if state not in ("main", "ai_tutor", "hw_add", "reminder_add", "club_name"):
        send_msg(user_id, "Не понял команду. Выбери в меню! 👇", keyboard=kb_main_menu())
    elif state in ("ai_tutor",):
        # В режиме ИИ-тьютора любой текст — это тема
        pass  # обработано выше
    else:
        send_msg(user_id, "Не понял. Выбери кнопку в меню! 👇", keyboard=kb_main_menu())

# ============================================================
#  ЗАПУСК
# ============================================================

def main():
    init_db()
    setup_scheduler()
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=scheduler.start, daemon=True)
    scheduler_thread.start()
    logging.info("Планировщик фоновых задач запущен.")

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    longpoll = VkLongPoll(vk_session)
    vk = vk_session.get_api()
    logging.info("Бот «Навигатор успеха» запущен. Ожидание сообщений...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            try:
                handle_message(event, vk)
            except Exception as e:
                logging.error(f"Error handling message: {e}", exc_info=True)
                try:
                    send_msg(event.user_id, "Ой, что-то пошло не так 😵 Попробуй ещё раз или нажми «🏠 Меню».", keyboard=kb_main_menu())
                except:
                    pass

if __name__ == "__main__":
    main()
