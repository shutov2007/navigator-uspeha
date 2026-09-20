# ============================================================
#  НАВИГАТОР УСПЕХА — чат-бот для ВКонтакте
#  Команда «Адреналин» · Конкурс «Технологии Первых»
#  Python 3.10+ · VK Long Poll · PostgreSQL · GigaChat · APScheduler
# ============================================================

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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  КОНФИГУРАЦИЯ
# ============================================================

VK_TOKEN = os.getenv("VK_TOKEN", "")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v2/chat/completions"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "dbname": os.getenv("DB_NAME", "navigator"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "port": int(os.getenv("DB_PORT", "5432")),
}

REMINDER_CHECK_MINUTES = 5  # как часто проверять напоминания
HW_REMINDER_HOUR = 19        # час напоминания о ДЗ (за день до дедлайна)
MORNING_HOUR = 7             # час утреннего приветствия
EVENING_HOUR = 21            # час вечернего пожелания
XP_ADD_HW = 10
XP_DONE_HW = 20
XP_QUIZ_CORRECT = 30
XP_STREAK_BONUS = 50
XP_LEVEL_THRESHOLD = 100  # каждые 100 XP = новый уровень

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
]
SPECIAL_SUBJECTS = ["Разговоры о важном", "Мои горизонты"]
ALL_SUBJECTS = SUBJECTS + SPECIAL_SUBJECTS

MORNING_PHRASES = [
    "Сегодня отличный день, чтобы сделать чуть больше, чем вчера! 💪",
    "Ты справишься со всем, что запланировано — шаг за шагом. ✨",
    "Помни: даже маленькие шаги ведут к большим победам! 🚀",
    "Новый день — новые возможности. Используй их по максимуму! 🌟",
    "Ты умнее и сильнее, чем думаешь. Доверяй себе! 🧠",
    "Каждый урок — это кирпичик твоего будущего. Строй его с умом! 🧱",
]

EVENING_PHRASES = [
    "Ты сегодня много сделал — пора отдохнуть и набраться сил! 🌙",
    "День был насыщенным, ты молодец! Завтра будет новый шанс. ✨",
    "Спокойной ночи! Пусть завтра всё получится ещё лучше. 💤",
    "Гордись тем, что сделал сегодня. Остальное — завтра. 🌛",
    "Отдых — это тоже часть обучения. Набирайся сил! 🔋",
]

ANTISTRESS = "Помни: можно сделать только самое важное, остальное — завтра. Ты не робот! 🤗"

BADGES = {
    1: "🌟 Новичок",
    2: "📚 Знаток",
    3: "🔥 Профи",
    4: "🏆 Мастер",
    5: "👑 Легенда",
}

LEVEL_NAMES = {
    1: "Новичок",
    2: "Знаток",
    3: "Профи",
    4: "Мастер",
    5: "Легенда",
    6: "Супергерой",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
#  БАЗА ДАННЫХ
# ============================================================

def db_conn():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    with db_conn() as conn:
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
                    last_active TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW()
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
                    start_time TIME NOT NULL,
                    UNIQUE(vk_id, day_of_week, start_time)
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
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
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
                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id SERIAL PRIMARY KEY,
                    vk_id BIGINT REFERENCES users(vk_id) ON DELETE CASCADE,
                    correct_answer TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS user_state (
                    vk_id BIGINT PRIMARY KEY REFERENCES users(vk_id) ON DELETE CASCADE,
                    state TEXT,
                    data TEXT
                )
            """)
        conn.commit()
    logger.info("База данных инициализирована.")

# --- Users ---
def get_user(vk_id: int) -> Optional[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE vk_id = %s", (vk_id,))
            return cur.fetchone()

def create_user(vk_id: int, username: str) -> Dict:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (vk_id, username) VALUES (%s, %s) "
                "ON CONFLICT (vk_id) DO UPDATE SET username = EXCLUDED.username "
                "RETURNING *",
                (vk_id, username)
            )
            conn.commit()
            return cur.fetchone()

def set_class(vk_id: int, class_grade: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET class_grade = %s WHERE vk_id = %s", (class_grade, vk_id))
            conn.commit()

def give_xp(vk_id: int, amount: int):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "UPDATE users SET xp = xp + %s, last_active = NOW() WHERE vk_id = %s RETURNING xp, level",
                (amount, vk_id)
            )
            row = cur.fetchone()
            conn.commit()
            if row:
                new_level = row["xp"] // XP_LEVEL_THRESHOLD + 1
                if new_level > row["level"]:
                    cur.execute("UPDATE users SET level = %s WHERE vk_id = %s", (new_level, vk_id))
                    conn.commit()
                    return new_level
    return None

def update_streak(vk_id: int):
    today = date.today()
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT last_streak_date, streak_days FROM users WHERE vk_id = %s", (vk_id,))
            row = cur.fetchone()
            if not row:
                return
            if row["last_streak_date"] is None:
                cur.execute("UPDATE users SET streak_days = 1, last_streak_date = %s WHERE vk_id = %s", (today, vk_id))
            elif row["last_streak_date"] == today - timedelta(days=1):
                new_streak = row["streak_days"] + 1
                cur.execute("UPDATE users SET streak_days = %s, last_streak_date = %s WHERE vk_id = %s",
                            (new_streak, today, vk_id))
            elif row["last_streak_date"] != today:
                cur.execute("UPDATE users SET streak_days = 1, last_streak_date = %s WHERE vk_id = %s", (today, vk_id))
            conn.commit()

# --- Schedule ---
def add_lesson(vk_id: int, day: int, subject: str, start_time: str, is_special: bool = False):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_schedule (vk_id, day_of_week, subject, start_time, is_special) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (vk_id, day, subject, start_time, is_special)
            )
            conn.commit()

def get_schedule_day(vk_id: int, day: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM user_schedule WHERE vk_id = %s AND day_of_week = %s ORDER BY start_time",
                (vk_id, day)
            )
            return cur.fetchall()

def get_schedule_all(vk_id: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM user_schedule WHERE vk_id = %s ORDER BY day_of_week, start_time",
                (vk_id,)
            )
            return cur.fetchall()

def delete_lesson(vk_id: int, lesson_id: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_schedule WHERE id = %s AND vk_id = %s", (lesson_id, vk_id))
            conn.commit()

# --- Clubs ---
def add_club(vk_id: int, name: str, day: int, start_time: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extracurriculars (vk_id, name, day_of_week, start_time) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (vk_id, name, day, start_time)
            )
            conn.commit()

def get_clubs_all(vk_id: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM extracurriculars WHERE vk_id = %s ORDER BY day_of_week, start_time",
                (vk_id,)
            )
            return cur.fetchall()

def get_clubs_day(vk_id: int, day: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM extracurriculars WHERE vk_id = %s AND day_of_week = %s ORDER BY start_time",
                (vk_id, day)
            )
            return cur.fetchall()

def delete_club(vk_id: int, club_id: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM extracurriculars WHERE id = %s AND vk_id = %s", (club_id, vk_id))
            conn.commit()

# --- Homework ---
def add_homework(vk_id: int, subject: str, description: str, due_date: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO homework (vk_id, subject, description, due_date) VALUES (%s, %s, %s, %s)",
                (vk_id, subject, description, due_date)
            )
            conn.commit()

def get_pending_hw(vk_id: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM homework WHERE vk_id = %s AND is_done = FALSE ORDER BY due_date",
                (vk_id,)
            )
            return cur.fetchall()

def mark_hw_done(vk_id: int, hw_id: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE homework SET is_done = TRUE WHERE id = %s AND vk_id = %s", (hw_id, vk_id))
            conn.commit()

def get_hw_stats(vk_id: int) -> Dict:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM homework WHERE vk_id = %s", (vk_id,))
            total = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS done FROM homework WHERE vk_id = %s AND is_done = TRUE", (vk_id,))
            done = cur.fetchone()["done"]
    return {"total": total, "done": done, "percent": round(done / total * 100) if total > 0 else 0}

# --- Reminders ---
def add_reminder(vk_id: int, text: str, trigger_time: datetime):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (vk_id, text, trigger_time) VALUES (%s, %s, %s)",
                (vk_id, text, trigger_time)
            )
            conn.commit()

def get_active_reminders(vk_id: int) -> List[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE vk_id = %s AND is_active = TRUE ORDER BY trigger_time",
                (vk_id,)
            )
            return cur.fetchall()

def get_today_reminders(vk_id: int) -> List[Dict]:
    today = date.today()
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE vk_id = %s AND is_active = TRUE "
                "AND trigger_time::date = %s ORDER BY trigger_time",
                (vk_id, today)
            )
            return cur.fetchall()

def delete_reminder(vk_id: int, rem_id: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reminders WHERE id = %s AND vk_id = %s", (rem_id, vk_id))
            conn.commit()

def toggle_reminder(vk_id: int, rem_id: int):
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT is_active FROM reminders WHERE id = %s AND vk_id = %s", (rem_id, vk_id))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE reminders SET is_active = NOT is_active WHERE id = %s", (rem_id,))
                conn.commit()

# --- User state ---
def set_state(vk_id: int, state: str, data: str = ""):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_state (vk_id, state, data) VALUES (%s, %s, %s) "
                "ON CONFLICT (vk_id) DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data",
                (vk_id, state, data)
            )
            conn.commit()

def get_state(vk_id: int) -> Optional[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM user_state WHERE vk_id = %s", (vk_id,))
            return cur.fetchone()

def clear_state(vk_id: int):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_state WHERE vk_id = %s", (vk_id,))
            conn.commit()

# --- Quiz sessions ---
def save_quiz(vk_id: int, correct_answer: str) -> int:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO quiz_sessions (vk_id, correct_answer) VALUES (%s, %s) RETURNING id",
                (vk_id, correct_answer)
            )
            row = cur.fetchone()
            conn.commit()
            return row["id"] if row else 0

def get_latest_quiz(vk_id: int) -> Optional[Dict]:
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM quiz_sessions WHERE vk_id = %s ORDER BY created_at DESC LIMIT 1",
                (vk_id,)
            )
            return cur.fetchone()

# --- HW reminders sent ---
def is_hw_reminder_sent(hw_id: int, sent_date: date) -> bool:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM hw_reminders_sent WHERE hw_id = %s AND sent_date = %s",
                (hw_id, sent_date)
            )
            return cur.fetchone() is not None

def mark_hw_reminder_sent(hw_id: int, sent_date: date):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hw_reminders_sent (hw_id, sent_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (hw_id, sent_date)
            )
            conn.commit()

# ============================================================
#  GIGACHAT
# ============================================================

_gigachat_token = None
_gigachat_token_expires = None

def get_gigachat_token() -> Optional[str]:
    global _gigachat_token, _gigachat_token_expires
    if _gigachat_token and _gigachat_token_expires and datetime.now() < _gigachat_token_expires:
        return _gigachat_token
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.post(
            GIGACHAT_AUTH_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": hashlib.uuid4().hex,
            },
            data={
                "scope": GIGACHAT_SCOPE,
            },
            auth=(GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET),
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _gigachat_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        _gigachat_token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        return _gigachat_token
    except Exception as e:
        logger.error(f"GigaChat auth error: {e}")
        return None

def hash_topic(topic: str, class_grade: int) -> str:
    return hashlib.sha256(f"{topic}:{class_grade}".encode()).hexdigest()

def get_cached(topic_hash: str) -> Optional[Dict]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT response_json FROM gigachat_cache WHERE topic_hash = %s", (topic_hash,))
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
    return None

def save_cache(topic_hash: str, data: Dict):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gigachat_cache (topic_hash, response_json) VALUES (%s, %s) "
                "ON CONFLICT (topic_hash) DO UPDATE SET response_json = EXCLUDED.response_json",
                (topic_hash, json.dumps(data, ensure_ascii=False))
            )
            conn.commit()

def call_gigachat(topic: str, class_grade: int) -> Optional[Dict]:
    topic_hash = hash_topic(topic, class_grade)
    cached = get_cached(topic_hash)
    if cached:
        logger.info(f"GigaChat cache hit: {topic}")
        return cached

    token = get_gigachat_token()
    if not token:
        return None

    prompt = (
        f"Объясни тему \"{topic}\" для ученика {class_grade} класса простым языком, "
        "как будто ты добрый школьный учитель. Используй примеры из жизни (еда, игры, спорт). "
        "Не пиши слишком длинно — 3-4 абзаца максимум. "
        "В конце задай 1 проверочный вопрос с 3 вариантами ответа (А, Б, В). "
        "Ответ верни СТРОГО в формате JSON без markdown:\n"
        '{"explanation": "текст объяснения", "question": "текст вопроса", '
        '"options": {"А": "вариант А", "Б": "вариант Б", "В": "вариант В"}, "correct": "А"}'
    )

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.post(
            GIGACHAT_CHAT_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "model": "GigaChat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            verify=False,
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(content)
        save_cache(topic_hash, data)
        logger.info(f"GigaChat success: {topic}")
        return data
    except Exception as e:
        logger.error(f"GigaChat call error: {e}")
        return None

# ============================================================
#  КЛАВИАТУРЫ
# ============================================================

def kb_main() -> VkKeyboard:
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
    kb.add_button("📋 Расписание", color=VkKeyboardColor.PRIMARY)
    kb.add_button("🎯 Кружки", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🤝 Поделиться", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_schedule_menu() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить урок", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("📋 Моё расписание", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("❌ Удалить урок", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_clubs_menu() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить кружок", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("📋 Мои кружки", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("❌ Удалить кружок", color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_hw_menu() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить ДЗ", color=VkKeyboardColor.POSITIVE)
    kb.add_button("📋 Мои ДЗ", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("✅ Отметить выполненным", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_reminders_menu() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить напоминание", color=VkKeyboardColor.POSITIVE)
    kb.add_button("📋 Сегодня", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("📋 Все напоминания", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("❌ Удалить", color=VkKeyboardColor.NEGATIVE)
    kb.add_button("🔄 Вкл/Выкл", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("🔙 Назад", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_days() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    for day_num in [1, 2, 3, 4]:
        kb.add_button(DAYS[day_num], color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    for day_num in [5, 6, 7]:
        kb.add_button(DAYS[day_num], color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🔙 Отмена", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_lesson_times() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    for i, t in enumerate(LESSON_TIMES):
        kb.add_button(t, color=VkKeyboardColor.PRIMARY)
        if i < len(LESSON_TIMES) - 1 and (i + 1) % 3 == 0:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Отмена", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_club_times() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    for i, t in enumerate(CLUB_TIMES):
        kb.add_button(t, color=VkKeyboardColor.PRIMARY)
        if i < len(CLUB_TIMES) - 1 and (i + 1) % 3 == 0:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Отмена", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_subjects() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    for i, subj in enumerate(ALL_SUBJECTS):
        color = VkKeyboardColor.POSITIVE if subj in SPECIAL_SUBJECTS else VkKeyboardColor.SECONDARY
        kb.add_button(subj, color=color)
        if i < len(ALL_SUBJECTS) - 1 and (i + 1) % 2 == 0:
            kb.add_line()
    kb.add_line()
    kb.add_button("🔙 Отмена", color=VkKeyboardColor.SECONDARY)
    return kb

def kb_quiz(options: Dict[str, str]) -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    for key in ["А", "Б", "В"]:
        if key in options:
            kb.add_button(f"{key}: {options[key]}", color=VkKeyboardColor.PRIMARY)
            kb.add_line()
    return kb

def kb_back() -> VkKeyboard:
    kb = VkKeyboard(one_time=False)
    kb.add_button("🔙 В меню", color=VkKeyboardColor.SECONDARY)
    return kb

# ============================================================
#  ОТПРАВКА СООБЩЕНИЙ
# ============================================================

_vk_session = None
_vk = None

def get_vk():
    global _vk_session, _vk
    if _vk is None:
        _vk_session = vk_api.VkApi(token=VK_TOKEN)
        _vk = _vk_session.get_api()
    return _vk

def send_msg(peer_id: int, text: str, keyboard: VkKeyboard = None):
    vk = get_vk()
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=text,
            keyboard=keyboard.get_keyboard() if keyboard else None,
            random_id=random.randint(0, 2**31),
        )
    except Exception as e:
        logger.error(f"Send msg error: {e}")

def send_typing(peer_id: int):
    vk = get_vk()
    try:
        vk.messages.setActivity(peer_id=peer_id, type="typing")
    except:
        pass

# ============================================================
#  ФОРМАТИРОВАНИЕ ТЕКСТОВ
# ============================================================

def load_emoji_scale(count: int) -> str:
    filled = min(count, 10)
    return "😵" * filled + "⬜" * (10 - filled)

def format_day_schedule(vk_id: int, day: int) -> str:
    lessons = get_schedule_day(vk_id, day)
    clubs = get_clubs_day(vk_id, day)
    day_name = DAYS.get(day, "?")
    text = f"📅 {day_name}:\n\n"
    if not lessons and not clubs:
        return text + "Нет уроков и кружков — свободный день! 🎉"
    if lessons:
        text += "Уроки:\n"
        for l in lessons:
            tag = " 🟢" if l["is_special"] else ""
            text += f"  ⏰ {l['start_time'].strftime('%H:%M')} — {l['subject']}{tag}\n"
    if clubs:
        text += "\nКружки и секции:\n"
        for c in clubs:
            text += f"  🎯 {c['start_time'].strftime('%H:%M')} — {c['name']}\n"
    total = len(lessons) + len(clubs)
    text += f"\n📊 Всего: {total} занятий. Нагрузка: {load_emoji_scale(total)}"
    if total >= 7:
        text += f"\n\n{ANTISTRESS}"
    return text

def format_full_schedule(vk_id: int) -> str:
    text = "📋 Моё расписание на неделю:\n\n"
    for day_num in range(1, 8):
        day_text = format_day_schedule(vk_id, day_num)
        text += day_text + "\n"
    return text

def format_progress(vk_id: int) -> str:
    u = get_user(vk_id)
    if not u:
        return "Не нашёл твои данные."
    stats = get_hw_stats(vk_id)
    level = u["xp"] // XP_LEVEL_THRESHOLD + 1
    level_name = LEVEL_NAMES.get(level, "Супергерой")
    badge = BADGES.get(level, "🏆")
    text = (
        f"📊 Твой прогресс:\n\n"
        f"🏆 Уровень: {level} ({level_name})\n"
        f"{badge} Значок: {badge}\n"
        f"⭐ XP: {u['xp']}\n"
        f"🔥 Стрик: {u['streak_days']} дн. подряд\n"
        f"📚 ДЗ выполнено: {stats['done']} из {stats['total']} ({stats['percent']}%)\n\n"
    )
    next_level_xp = level * XP_LEVEL_THRESHOLD
    xp_left = next_level_xp - u["xp"]
    text += f"До следующего уровня: {xp_left} XP 💪\n"
    return text

def format_hw_list(vk_id: int) -> str:
    hw_list = get_pending_hw(vk_id)
    if not hw_list:
        return "🎉 У тебя нет невыполненных ДЗ! Ты молодец! 🌟"
    text = "📋 Твои невыполненные ДЗ:\n\n"
    for hw in hw_list:
        due = hw["due_date"]
        due_str = due.strftime("%d.%m.%Y") if isinstance(due, date) else str(due)
        text += f"🆔 {hw['id']}  📘 {hw['subject']}\n📝 {hw['description']}\n🗓 До: {due_str}\n\n"
    text += "Чтобы отметить выполненным — нажми «✅ Отметить» и отправь ID."
    return text

def format_reminders_list(vk_id: int, today_only: bool = False) -> str:
    rems = get_today_reminders(vk_id) if today_only else get_active_reminders(vk_id)
    title = "📋 Напоминания на сегодня:" if today_only else "📋 Все активные напоминания:"
    if not rems:
        return title + "\n\nПусто — нет активных напоминаний."
    text = title + "\n\n"
    for r in rems:
        t = r["trigger_time"]
        t_str = t.strftime("%d.%m.%Y %H:%M") if isinstance(t, datetime) else str(t)
        status = "✅" if r["is_active"] else "❌"
        text += f"🆔 {r['id']}  {status}  ⏰ {t_str}\n📝 {r['text']}\n\n"
    text += "ID нужен для удаления и вкл/выкл."
    return text

def format_clubs_list(vk_id: int) -> str:
    clubs = get_clubs_all(vk_id)
    if not clubs:
        return "У тебя пока нет кружков и секций. Добавь через «➕ Добавить кружок»!"
    text = "🎯 Твои кружки и секции:\n\n"
    for c in clubs:
        text += f"🆔 {c['id']}  📅 {DAYS[c['day_of_week']]}  ⏰ {c['start_time'].strftime('%H:%M')} — {c['name']}\n"
    text += "\nЧтобы удалить — нажми «❌ Удалить» и отправь ID."
    return text

# ============================================================
#  ФОНОВЫЕ ЗАДАЧИ (APScheduler)
# ============================================================

def morning_job():
    logger.info("Запуск утренней рассылки...")
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            users = cur.fetchall()
    for u in users:
        try:
            today = datetime.now().weekday() + 1
            lessons = get_schedule_day(u["vk_id"], today)
            clubs = get_clubs_day(u["vk_id"], today)
            total = len(lessons) + len(clubs)
            phrase = random.choice(MORNING_PHRASES)
            name = u["username"] or "друг"
            text = f"Доброе утро, {name}! 🌞\n\n"
            text += f"Сегодня у тебя {len(lessons)} уроков и {len(clubs)} кружков.\n"
            text += f"Нагрузка: {load_emoji_scale(total)}\n"
            if total >= 7:
                text += f"\n{ANTISTRESS}\n"
            text += f"\n{phrase}\n\n"
            text += "План на день — в разделе «📅 Что сегодня?». Удачи! 🍀"
            send_msg(u["vk_id"], text)
        except Exception as e:
            logger.error(f"Morning job failed for {u['vk_id']}: {e}")

def evening_job():
    logger.info("Запуск вечерней рассылки...")
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            users = cur.fetchall()
    for u in users:
        try:
            hw = get_pending_hw(u["vk_id"])
            phrase = random.choice(EVENING_PHRASES)
            name = u["username"] or "друг"
            text = f"Спокойной ночи, {name}! 🌙\n\n"
            text += f"У тебя осталось {len(hw)} невыполненных ДЗ.\n"
            text += f"Не переживай — завтра разберёшься!\n\n"
            text += f"{phrase}\n\n"
            text += "Я буду здесь утром. Отдыхай! 💤"
            send_msg(u["vk_id"], text)
        except Exception as e:
            logger.error(f"Evening job failed for {u['vk_id']}: {e}")

def check_reminders_job():
    now = datetime.now()
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE trigger_time <= %s AND is_active = TRUE",
                (now,)
            )
            rems = cur.fetchall()
    for r in rems:
        try:
            send_msg(r["vk_id"], f"⏰ Напоминание!\n\n{r['text']}")
            with db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE reminders SET is_active = FALSE WHERE id = %s", (r["id"],))
                    conn.commit()
            logger.info(f"Reminder sent: {r['id']} to {r['vk_id']}")
        except Exception as e:
            logger.error(f"Reminder send failed: {e}")

def check_hw_job():
    now = datetime.now()
    if now.hour < HW_REMINDER_HOUR:
        return
    tomorrow = now.date() + timedelta(days=1)
    if is_hw_reminder_sent(0, now.date()):
        pass
    with db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT h.*, u.username FROM homework h
                JOIN users u ON h.vk_id = u.vk_id
                WHERE h.is_done = FALSE AND h.due_date = %s
            """, (tomorrow,))
            hw_list = cur.fetchall()
    for hw in hw_list:
        if is_hw_reminder_sent(hw["id"], now.date()):
            continue
        try:
            name = hw["username"] or "ученик"
            due = hw["due_date"]
            due_str = due.strftime("%d.%m") if isinstance(due, date) else str(due)
            text = (
                f"⏰ Внимание, {name}!\n\n"
                f"Завтра ({due_str}) дедлайн по ДЗ:\n"
                f"📘 {hw['subject']}\n"
                f"📝 {hw['description']}\n\n"
                f"Не забудь выполнить сегодня вечером! 💪"
            )
            send_msg(hw["vk_id"], text)
            mark_hw_reminder_sent(hw["id"], now.date())
            logger.info(f"HW reminder sent: hw_id={hw['id']} to {hw['vk_id']}")
        except Exception as e:
            logger.error(f"HW reminder failed: {e}")

# ============================================================
#  ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================

def handle_message(event):
    user_id = event.user_id
    raw_text = event.text or ""
    text = raw_text.strip().lower()
    user = get_user(user_id)
    state = get_state(user_id) if user else None

    # --- /start ---
    if text == "/start" or text == "начать" or text == "start":
        if not user:
            user = create_user(user_id, event.user_name or f"user_{user_id}")
            send_msg(user_id,
                "Привет! 👋 Я «Навигатор успеха» — твой помощник в учёбе.\n\n"
                "Я помогу с расписанием, ДЗ, напоминаниями и объясню сложные темы!\n\n"
                "В каком ты классе (5–9)? Напиши просто цифру."
            )
            return
        if not user["class_grade"]:
            send_msg(user_id, "В каком ты классе (5–9)? Напиши просто цифру.")
            return
        update_streak(user_id)
        send_msg(user_id, f"С возвращением, {user['username'] or 'друг'}! 🎉\nВыбирай в меню:", keyboard=kb_main())
        return

    # --- Установка класса ---
    if user and not user["class_grade"] and text.isdigit():
        grade = int(text)
        if 5 <= grade <= 9:
            set_class(user_id, grade)
            update_streak(user_id)
            send_msg(user_id,
                f"Отлично! Класс {grade} сохранён. 🎓\n"
                "Теперь я буду подстраивать объяснения под твою программу.\n\n"
                "Главное меню — ниже. Выбирай, что нужно!",
                keyboard=kb_main()
            )
            return
        else:
            send_msg(user_id, "Пожалуйста, напиши цифру от 5 до 9.")
            return

    # Если пользователь не зарегистрирован
    if not user:
        create_user(user_id, event.user_name or f"user_{user_id}")
        send_msg(user_id, "Привет! 👋 Напиши /start, чтобы начать.")
        return

    # Если класс не установлен
    if not user["class_grade"]:
        if text.isdigit():
            grade = int(text)
            if 5 <= grade <= 9:
                set_class(user_id, grade)
                send_msg(user_id, "Класс сохранён! 🎓 Выбирай в меню:", keyboard=kb_main())
                return
        send_msg(user_id, "В каком ты классе (5–9)? Напиши цифру.")
        return

    # --- Обработка состояний (пошаговый ввод) ---

    # Состояние: добавление ДЗ — ожидание формата
    if state and state["state"] == "hw_add":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено. Возврат в меню ДЗ.", keyboard=kb_hw_menu())
            return
        if "|" in raw_text:
            parts = [p.strip() for p in raw_text.split("|")]
            if len(parts) == 3:
                subject, description, due_date = parts
                try:
                    datetime.strptime(due_date, "%Y-%m-%d")
                    add_homework(user_id, subject, description, due_date)
                    new_level = give_xp(user_id, XP_ADD_HW)
                    msg = f"✅ ДЗ по «{subject}» на {due_date} добавлено! +{XP_ADD_HW} XP 🎉"
                    if new_level:
                        msg += f"\n\n🎊 Поздравляю! Ты перешёл на уровень {new_level} ({LEVEL_NAMES.get(new_level, 'Супергерой'})!)"
                    send_msg(user_id, msg, keyboard=kb_hw_menu())
                    clear_state(user_id)
                    return
                except ValueError:
                    send_msg(user_id, "❌ Неверный формат даты. Пример: 2024-12-20\n\nПопробуй ещё раз или нажми «🔙 Назад».")
                    return
        send_msg(user_id,
            "Отправь в одном сообщении:\n"
            "Предмет | Описание | Дата (ГГГГ-ММ-ДД)\n\n"
            "Пример: Математика | Упр. 12, стр. 45 | 2024-12-20\n\n"
            "Или нажми «🔙 Назад»."
        )
        return

    # Состояние: отметка ДЗ выполненным
    if state and state["state"] == "hw_done":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_hw_menu())
            return
        if text.isdigit():
            mark_hw_done(user_id, int(text))
            new_level = give_xp(user_id, XP_DONE_HW)
            msg = f"✅ ДЗ с ID {text} отмечено выполненным! +{XP_DONE_HW} XP 🎉"
            if new_level:
                msg += f"\n\n🎊 Уровень {new_level}! Ты {LEVEL_NAMES.get(new_level, 'Супергерой'})!"
            send_msg(user_id, msg, keyboard=kb_hw_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Отправь ID ДЗ (число). Например: 5\nИли нажми «🔙 Назад».")
        return

    # Состояние: добавление напоминания
    if state and state["state"] == "rem_add":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_reminders_menu())
            return
        if "|" in raw_text:
            parts = [p.strip() for p in raw_text.split("|")]
            if len(parts) == 2:
                rem_text, rem_time_str = parts
                try:
                    trigger = datetime.strptime(rem_time_str, "%Y-%m-%d %H:%M")
                    add_reminder(user_id, rem_text, trigger)
                    send_msg(user_id, f"✅ Напоминание «{rem_text}» добавлено на {rem_time_str}! ⏰",
                             keyboard=kb_reminders_menu())
                    clear_state(user_id)
                    return
                except ValueError:
                    pass
        send_msg(user_id,
            "Отправь: Текст | ГГГГ-ММ-ДД ЧЧ:ММ\n\n"
            "Пример: Сдать проект | 2024-12-25 18:00\n\n"
            "Или нажми «🔙 Назад»."
        )
        return

    # Состояние: удалить напоминание
    if state and state["state"] == "rem_del":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_reminders_menu())
            return
        if text.isdigit():
            delete_reminder(user_id, int(text))
            send_msg(user_id, f"✅ Напоминание {text} удалено.", keyboard=kb_reminders_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Отправь ID напоминания (число). Или «🔙 Назад».")
        return

    # Состояние: вкл/выкл напоминание
    if state and state["state"] == "rem_toggle":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_reminders_menu())
            return
        if text.isdigit():
            toggle_reminder(user_id, int(text))
            send_msg(user_id, f"✅ Статус напоминания {text} изменён.", keyboard=kb_reminders_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Отправь ID напоминания (число). Или «🔙 Назад».")
        return

    # Состояние: удалить урок
    if state and state["state"] == "lesson_del":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_schedule_menu())
            return
        if text.isdigit():
            delete_lesson(user_id, int(text))
            send_msg(user_id, f"✅ Урок {text} удалён.", keyboard=kb_schedule_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Отправь ID урока (число). Или «🔙 Назад».")
        return

    # Состояние: удалить кружок
    if state and state["state"] == "club_del":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_clubs_menu())
            return
        if text.isdigit():
            delete_club(user_id, int(text))
            send_msg(user_id, f"✅ Кружок {text} удалён.", keyboard=kb_clubs_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Отправь ID кружка (число). Или «🔙 Назад».")
        return

    # Состояние: выбор предмета для ИИ-тьютора (после выбора предмета)
    # (не используется — пользователь пишет тему текстом)

    # Состояние: добавление урока — выбран день, ждём время
    if state and state["state"] == "lesson_day":
        if "🔙" in text or "отмена" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_schedule_menu())
            return
        if text in [t.lower() for t in LESSON_TIMES]:
            day = int(state["data"])
            set_state(user_id, "lesson_time", f"{day}|{text}")
            send_msg(user_id, "Теперь выбери предмет:", keyboard=kb_subjects())
            return
        send_msg(user_id, "Выбери время кнопкой ниже.", keyboard=kb_lesson_times())
        return

    # Состояние: добавление урока — выбрано время, ждём предмет
    if state and state["state"] == "lesson_time":
        if "🔙" in text or "отмена" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_schedule_menu())
            return
        # Ищем предмет
        chosen = None
        for subj in ALL_SUBJECTS:
            if subj.lower() == text:
                chosen = subj
                break
        if chosen:
            parts = state["data"].split("|")
            day = int(parts[0])
            start_time = parts[1]
            is_special = chosen in SPECIAL_SUBJECTS
            add_lesson(user_id, day, chosen, start_time, is_special)
            new_level = give_xp(user_id, XP_ADD_HW)
            msg = f"✅ Урок добавлен: {DAYS[day]} ⏰ {start_time} — {chosen}{' 🟢' if is_special else ''}\n+{XP_ADD_HW} XP!"
            if new_level:
                msg += f"\n\n🎊 Уровень {new_level}! Ты {LEVEL_NAMES.get(new_level, 'Супергерой'})!"
            send_msg(user_id, msg, keyboard=kb_schedule_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Выбери предмет кнопкой ниже.", keyboard=kb_subjects())
        return

    # Состояние: добавление кружка — выбран день, ждём время
    if state and state["state"] == "club_day":
        if "🔙" in text or "отмена" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_clubs_menu())
            return
        if text in [t.lower() for t in CLUB_TIMES]:
            day = int(state["data"])
            set_state(user_id, "club_time", f"{day}|{text}")
            send_msg(user_id, "Теперь напиши название кружка или секции:\nНапример: Футбол, Хор, Робототехника")
            return
        send_msg(user_id, "Выбери время кнопкой ниже.", keyboard=kb_club_times())
        return

    # Состояние: добавление кружка — выбрано время, ждём название
    if state and state["state"] == "club_time":
        if "🔙" in text or "отмена" in text:
            clear_state(user_id)
            send_msg(user_id, "Отменено.", keyboard=kb_clubs_menu())
            return
        if len(raw_text) > 0 and len(raw_text) < 100:
            parts = state["data"].split("|")
            day = int(parts[0])
            start_time = parts[1]
            add_club(user_id, raw_text.strip(), day, start_time)
            new_level = give_xp(user_id, XP_ADD_HW)
            msg = f"✅ Кружок добавлен: {DAYS[day]} ⏰ {start_time} — {raw_text.strip()}\n+{XP_ADD_HW} XP!"
            if new_level:
                msg += f"\n\n🎊 Уровень {new_level}! Ты {LEVEL_NAMES.get(new_level, 'Супергерой'})!"
            send_msg(user_id, msg, keyboard=kb_clubs_menu())
            clear_state(user_id)
            return
        send_msg(user_id, "Напиши название кружка (до 100 символов).")
        return

    # Состояние: ИИ-тьютор — проверка ответа на квиз
    if state and state["state"] == "quiz_wait":
        quiz = get_latest_quiz(user_id)
        if quiz:
            correct = quiz["correct_answer"]
            # Извлекаем букву ответа (первые символы до ":" или сама буква)
            answer_letter = ""
            if ":" in raw_text:
                answer_letter = raw_text.split(":")[0].strip().upper()
            else:
                answer_letter = raw_text.strip().upper()
            # Маппинг латинских А/B/C в кириллицу
            letter_map = {"A": "А", "B": "Б", "C": "В", "А": "А", "Б": "Б", "В": "В"}
            answer_letter = letter_map.get(answer_letter, answer_letter)
            if answer_letter == correct:
                new_level = give_xp(user_id, XP_QUIZ_CORRECT)
                msg = f"✅ Верно! +{XP_QUIZ_CORRECT} XP 🎉"
                if new_level:
                    msg += f"\n\n🎊 Уровень {new_level}! Ты {LEVEL_NAMES.get(new_level, 'Супергерой'})!"
                msg += "\n\nХочешь разобрать ещё одну тему? Напиши её название!"
            else:
                msg = f"❌ Не совсем так. Правильный ответ: {correct}\n\nНе переживай — ошибки помогают учиться! Попробуй другую тему?"
            send_msg(user_id, msg, keyboard=kb_main())
            clear_state(user_id)
            return

    # --- КНОПКИ ГЛАВНОГО МЕНЮ ---

    # Что сегодня?
    if "что сегодня" in text:
        today = datetime.now().weekday() + 1
        send_msg(user_id, format_day_schedule(user_id, today), keyboard=kb_main())
        return

    # ИИ-тьютор
    if "ии-тьютор" in text or "ии тьютор" in text or "тьютор" in text:
        send_msg(user_id,
            "📚 ИИ-тьютор на базе GigaChat!\n\n"
            "Напиши тему, которую не понял — например:\n"
            "«дроби», «Past Simple», «закон Ома», «клетка»\n\n"
            "Я объясню простыми словами с примерами и задам проверочный вопрос!"
        )
        set_state(user_id, "tutor_wait")
        return

    # ДЗ
    if text == "🎒 дз" or text == "дз":
        send_msg(user_id, "🎒 Управление ДЗ:\n\nВыбери действие:", keyboard=kb_hw_menu())
        return

    # Напоминания
    if "напоминания" in text and "🔙" not in text:
        send_msg(user_id, "🔔 Напоминания:\n\nВыбери действие:", keyboard=kb_reminders_menu())
        return

    # Прогресс
    if "прогресс" in text:
        update_streak(user_id)
        send_msg(user_id, format_progress(user_id), keyboard=kb_main())
        return

    # Учёба (ссылки)
    if "учёба" in text or "учеба" in text:
        links = (
            "🔗 Полезные ресурсы для учёбы:\n\n"
            "📘 ЦОК (Цифровые образовательные контенты): https://m.edsoo.ru\n"
            "📚 Учи.ру: https://uchi.ru\n"
            "📖 Яндекс.Учебник: https://education.yandex.ru\n"
            "🎓 Stepik: https://stepik.org\n"
            "🧠 Skysmart: https://skysmart.ru\n"
            "📐 ФизМатБанк (задачи): https://fizmatbank.ru\n"
            "🔬 Единая коллекция ЦОР: http://school-collection.edu.ru\n\n"
            "Все ресурсы разрешены в РФ ✅"
        )
        send_msg(user_id, links, keyboard=kb_main())
        return

    # Расписание
    if "расписание" in text and "поделиться" not in text:
        send_msg(user_id, "📋 Управление расписанием:\n\nВыбери действие:", keyboard=kb_schedule_menu())
        return

    # Кружки
    if "кружки" in text and "🎯" in text:
        send_msg(user_id, "🎯 Кружки и секции:\n\nВыбери действие:", keyboard=kb_clubs_menu())
        return

    # Поделиться
    if "поделиться" in text:
        today = datetime.now().weekday() + 1
        share = format_day_schedule(user_id, today)
        share += "\n\n📌 Скопируй и отправь однокласснику!"
        send_msg(user_id, share, keyboard=kb_main())
        return

    # --- КНОПКИ РАСПИСАНИЯ ---
    if "добавить урок" in text:
        send_msg(user_id, "Выбери день недели:", keyboard=kb_days())
        set_state(user_id, "lesson_day", "")
        return

    if "моё расписание" in text or "мое расписание" in text:
        send_msg(user_id, format_full_schedule(user_id), keyboard=kb_schedule_menu())
        return

    if "удалить урок" in text:
        lessons = get_schedule_all(user_id)
        if not lessons:
            send_msg(user_id, "У тебя пока нет уроков в расписании.", keyboard=kb_schedule_menu())
            return
        text_out = "Твои уроки:\n\n"
        for l in lessons:
            tag = " 🟢" if l["is_special"] else ""
            text_out += f"🆔 {l['id']}  📅 {DAYS[l['day_of_week']]}  ⏰ {l['start_time'].strftime('%H:%M')} — {l['subject']}{tag}\n"
        text_out += "\nОтправь ID урока для удаления:"
        send_msg(user_id, text_out)
        set_state(user_id, "lesson_del")
        return

    # --- КНОПКИ КРУЖКОВ ---
    if "добавить кружок" in text:
        send_msg(user_id, "Выбери день недели:", keyboard=kb_days())
        set_state(user_id, "club_day", "")
        return

    if "мои кружки" in text:
        send_msg(user_id, format_clubs_list(user_id), keyboard=kb_clubs_menu())
        return

    if "удалить кружок" in text:
        clubs = get_clubs_all(user_id)
        if not clubs:
            send_msg(user_id, "У тебя пока нет кружков.", keyboard=kb_clubs_menu())
            return
        text_out = "Твои кружки:\n\n"
        for c in clubs:
            text_out += f"🆔 {c['id']}  📅 {DAYS[c['day_of_week']]}  ⏰ {c['start_time'].strftime('%H:%M')} — {c['name']}\n"
        text_out += "\nОтправь ID кружка для удаления:"
        send_msg(user_id, text_out)
        set_state(user_id, "club_del")
        return

    # --- КНОПКИ ДЗ ---
    if "добавить дз" in text:
        send_msg(user_id,
            "➕ Добавление ДЗ\n\n"
            "Отправь в одном сообщении:\n"
            "Предмет | Описание | Дата (ГГГГ-ММ-ДД)\n\n"
            "Пример: Математика | Упр. 12, стр. 45 | 2024-12-20"
        )
        set_state(user_id, "hw_add")
        return

    if "мои дз" in text:
        send_msg(user_id, format_hw_list(user_id), keyboard=kb_hw_menu())
        return

    if "отметить выполненным" in text:
        hw = get_pending_hw(user_id)
        if not hw:
            send_msg(user_id, "🎉 Нет невыполненных ДЗ!", keyboard=kb_hw_menu())
            return
        send_msg(user_id, format_hw_list(user_id) + "\n\nОтправь ID ДЗ, которое выполнил:")
        set_state(user_id, "hw_done")
        return

    # --- КНОПКИ НАПОМИНАНИЙ ---
    if "добавить напоминание" in text:
        send_msg(user_id,
            "➕ Добавление напоминания\n\n"
            "Отправь: Текст | ГГГГ-ММ-ДД ЧЧ:ММ\n\n"
            "Пример: Сдать проект | 2024-12-25 18:00"
        )
        set_state(user_id, "rem_add")
        return

    if "сегодня" in text and state and state["state"] is None:
        # может быть из напоминаний
        pass

    # Кнопка "📋 Сегодня" в напоминаниях
    if text == "📋 сегодня" or (text == "сегодня" and "напоминания" not in text):
        rems = get_today_reminders(user_id)
        if not rems:
            send_msg(user_id, "📋 На сегодня нет напоминаний.", keyboard=kb_reminders_menu())
        else:
            send_msg(user_id, format_reminders_list(user_id, today_only=True), keyboard=kb_reminders_menu())
        return

    if "все напоминания" in text:
        send_msg(user_id, format_reminders_list(user_id), keyboard=kb_reminders_menu())
        return

    if text == "❌ удалить" or (text == "удалить" and "напоминания" not in text):
        rems = get_active_reminders(user_id)
        if not rems:
            send_msg(user_id, "Нет активных напоминаний для удаления.", keyboard=kb_reminders_menu())
            return
        send_msg(user_id, format_reminders_list(user_id) + "\n\nОтправь ID напоминания для удаления:")
        set_state(user_id, "rem_del")
        return

    if "вкл/выкл" in text or "вкл выкл" in text:
        rems = get_active_reminders(user_id)
        if not rems:
            send_msg(user_id, "Нет напоминаний.", keyboard=kb_reminders_menu())
            return
        send_msg(user_id, format_reminders_list(user_id) + "\n\nОтправь ID напоминания для переключения:")
        set_state(user_id, "rem_toggle")
        return

    # --- НАВИГАЦИЯ НАЗАД ---
    if "🔙" in text or "назад" in text:
        if "кружки" in text or state and state and state["state"] and "club" in state["state"]:
            send_msg(user_id, "🎯 Кружки и секции:", keyboard=kb_clubs_menu())
        elif state and state and state["state"] and "lesson" in state["state"]:
            send_msg(user_id, "📋 Расписание:", keyboard=kb_schedule_menu())
        else:
            send_msg(user_id, "Главное меню:", keyboard=kb_main())
        clear_state(user_id)
        return

    # --- ВЫБОР ДЛЯ ДНЕЙ НЕДЕЛИ (кнопки Пн-Вс) ---
    day_map_inv = {v.lower(): k for k, v in DAYS.items()}
    if text in day_map_inv:
        day = day_map_inv[text]
        if state and state["state"] == "lesson_day":
            set_state(user_id, "lesson_day", str(day))
            send_msg(user_id, f"День: {DAYS[day]}. Выбери время урока:", keyboard=kb_lesson_times())
            return
        elif state and state["state"] == "club_day":
            set_state(user_id, "club_day", str(day))
            send_msg(user_id, f"День: {DAYS[day]}. Выбери время кружка:", keyboard=kb_club_times())
            return

    # --- ИИ-ТЬЮТОР: обработка темы ---
    if state and state["state"] == "tutor_wait":
        if "🔙" in text or "назад" in text:
            clear_state(user_id)
            send_msg(user_id, "Возврат в меню.", keyboard=kb_main())
            return
        send_typing(user_id)
        send_msg(user_id, "🧠 Думаю над объяснением...")
        result = call_gigachat(raw_text.strip(), user["class_grade"])
        if result and "explanation" in result:
            explanation = result.get("explanation", "")
            question = result.get("question", "")
            options = result.get("options", {})
            correct = result.get("correct", "")
            text_out = f"📝 Тема: «{raw_text.strip()}»\n\n{explanation}\n\n"
            text_out += f"❓ Проверочный вопрос:\n{question}\n\n"
            for key in ["А", "Б", "В"]:
                if key in options:
                    text_out += f"{key}: {options[key]}\n"
            text_out += "\nВыбери ответ кнопкой ниже 👇"
            save_quiz(user_id, correct)
            set_state(user_id, "quiz_wait")
            # Клавиатура с вариантами
            kb = VkKeyboard(one_time=True)
            for key in ["А", "Б", "В"]:
                if key in options:
                    kb.add_button(f"{key}: {options[key]}", color=VkKeyboardColor.PRIMARY)
                    kb.add_line()
            send_msg(user_id, text_out, keyboard=kb)
        else:
            send_msg(user_id,
                "😔 К сожалению, не удалось подключиться к ИИ. Попробуй позже!\n\n"
                "А пока загляни в раздел «🔗 Учёба» — там есть полезные ссылки на видеоуроки.",
                keyboard=kb_main()
            )
            clear_state(user_id)
        return

    # --- Неизвестное сообщение ---
    # Проверим, может это ответ на квиз
    quiz = get_latest_quiz(user_id)
    if quiz and state and state["state"] == "quiz_wait":
        # Уже обработано выше, но на всякий случай
        pass

    send_msg(user_id,
        "Не понял команду 🤔\nВыбери действие в меню или напиши /start.",
        keyboard=kb_main()
    )

# ============================================================
#  ЗАПУСК БОТА
# ============================================================

def run_bot():
    init_db()
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    longpoll = VkLongPoll(vk_session)
    global _vk_session, _vk
    _vk_session = vk_session
    _vk = vk_session.get_api()

    # APScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(morning_job, CronTrigger(hour=MORNING_HOUR, minute=0))
    scheduler.add_job(evening_job, CronTrigger(hour=EVENING_HOUR, minute=0))
    scheduler.add_job(check_reminders_job, "interval", minutes=REMINDER_CHECK_MINUTES)
    scheduler.add_job(check_hw_job, "interval", minutes=30)
    scheduler.start()
    logger.info("Scheduler запущен.")

    logger.info("Бот «Навигатор успеха» запущен. Ожидание сообщений...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            try:
                handle_message(event)
            except Exception as e:
                logger.error(f"Ошибка обработки: {e}", exc_info=True)
                try:
                    send_msg(event.user_id, "Ой, что-то пошло не так 🙈 Попробуй ещё раз или /start.")
                except:
                    pass

if __name__ == "__main__":
    run_bot()
