# -*- coding: utf-8 -*-
"""
================================================================================
    НАВИГАТОР УСПЕХА — VK-бот с интеграцией GigaChat
    Версия: 2.0.0
    Автор: LifeCode Studio
================================================================================

    Полнофункциональный бот для ВКонтакте, который:
      - Регистрирует и ведёт пользователей
      - Хранит историю диалогов в PostgreSQL
      - Интегрируется с GigaChat для генерации ответов
      - Поддерживает админ-команды и статистику
      - Имеет защиту от спама и систему логирования
      - Обрабатывает ошибки на всех уровнях
      - Поддерживает Long Polling для получения сообщений

    Файл: navigator_bot.py
    Требования: Python 3.10+, PostgreSQL 14+, VK API, GigaChat API
================================================================================
"""

import os
import sys
import time
import json
import logging
import logging.handlers
import traceback
import signal
import threading
import queue
import hashlib
import re
import datetime
import random
import socket
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto

# --- Внешние библиотеки ---
try:
    from dotenv import load_dotenv
except ImportError:
    print("КРИТИЧНО: библиотека python-dotenv не установлена!")
    print("Выполните: pip install python-dotenv")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2 import pool, errors as pg_errors, sql
    from psycopg2.extras import RealDictCursor, Json
except ImportError:
    print("КРИТИЧНО: библиотека psycopg2 не установлена!")
    print("Выполните: pip install psycopg2-binary")
    sys.exit(1)

try:
    import vk_api
    from vk_api.exceptions import ApiError, VkApiError
except ImportError:
    print("КРИТИЧНО: библиотека vk_api не установлена!")
    print("Выполните: pip install vk_api")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("КРИТИЧНО: библиотека requests не установлена!")
    print("Выполните: pip install requests")
    sys.exit(1)


# =============================================================================
# КОНСТАНТЫ И КОНФИГУРАЦИЯ
# =============================================================================

BOT_NAME = "Навигатор Успеха"
BOT_VERSION = "2.0.0"
BOT_AUTHOR = "LifeCode Studio"

# Параметры БД
DB_MIN_CONNECTIONS = 2
DB_MAX_CONNECTIONS = 10
DB_CONNECTION_TIMEOUT = 10  # секунд

# Параметры VK Long Polling
VK_LONG_POLL_WAIT = 25  # секунд ожидания сервера
VK_LONG_POLL_MODE = 234  # режим получения событий (сообщения + расширения)
VK_LONG_POLL_VERSION = 3
VK_API_VERSION = "5.199"

# Параметры GigaChat
GIGACHAT_API_URL = "https://gigachat.devicespace.ru/gigachat/v1"
GIGACHAT_AUTH_URL = "https://gigachat.devicespace.ru/gigachat/api/v5"
GIGACHAT_TIMEOUT = 60  # секунд на ответ
GIGACHAT_MAX_RETRIES = 3
GIGACHAT_RETRY_DELAY = 2  # секунд между попытками
GIGACHAT_MODEL = "GigaChat-Pro"

# Параметры бота
MAX_MESSAGE_LENGTH = 4096  # максимум символов в одном сообщении VK
MAX_HISTORY_MESSAGES = 20  # сколько сообщений истории отправлять в GigaChat
ADMIN_COMMAND_PREFIX = "!"
ANTISPAM_WINDOW = 10  # секунд — окно для подсчёта сообщений от одного юзера
ANTISPAM_MAX_MESSAGES = 5  # максимум сообщений в окне
ANTISPAM_BAN_DURATION = 300  # секунд — на сколько банить за спам
MAX_RETRIES_VK = 3  # попыток отправки сообщения
VK_SEND_DELAY = 0.05  # задержка между отправкой (для лимитов API)
HEALTH_CHECK_INTERVAL = 300  # секунд между проверками здоровья (5 минут)
STATS_DUMP_INTERVAL = 3600  # секунд между дампом статистики (1 час)

# Системный промпт для GigaChat
SYSTEM_PROMPT = (
    "Ты — Навигатор Успеха, виртуальный помощник для предпринимателей и "
    "саморазвития. Твоя задача — помогать людям находить путь к успеху, "
    "давать мотивирующие советы, помогать с бизнес-идеями, планированием "
    "и саморазвитием. Отвечай на русском языке, будь дружелюбным, "
    "кратким, но информативным. Используй эмодзи умеренно. "
    "Если не знаешь ответ — честно скажи об этом. "
    "Не давай финансовых гарантий и медицинских советов."
)

# Приветственное сообщение
WELCOME_MESSAGE = (
    "🌟 Добро пожаловать в «Навигатор Успеха»!\n\n"
    "Я — твой виртуальный помощник на пути к целям. "
    "Задавай любые вопросы о бизнесе, саморазвитии, "
    "мотивации — и я постараюсь помочь!\n\n"
    "Команды:\n"
    "  !help — список команд\n"
    "  !stats — твоя статистика\n"
    "  !clear — очистить историю диалога\n"
    "  !about — информация о боте\n\n"
    "🚀 Поехали!"
)

HELP_MESSAGE = (
    "📖 Справка по командам:\n\n"
    "!help — эта справка\n"
    "!stats — твоя личная статистика\n"
    "!clear — очистить историю диалога\n"
    "!about — информация о боте\n"
    "!top — топ активных пользователей (для всех)\n\n"
    "Просто напиши сообщение — и я отвечу!"
)

ABOUT_MESSAGE = (
    f"ℹ️ {BOT_NAME} v{BOT_VERSION}\n\n"
    f"Разработчик: {BOT_AUTHOR}\n"
    "Технологии: Python, PostgreSQL, VK API, GigaChat\n"
    "Бот создан для помощи в саморазвитии и бизнесе.\n\n"
    "Спасибо, что выбрали нас! 🙏"
)


# =============================================================================
# ПЕРЕЧИСЛЕНИЯ
# =============================================================================

class UserRole(Enum):
    """Роли пользователей в системе."""
    USER = "user"
    ADMIN = "admin"
    BANNED = "banned"


class UserStatus(Enum):
    """Статус пользователя."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


class MessageType(Enum):
    """Типы сообщений в истории."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class BotState(Enum):
    """Состояния бота."""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


class LogLevel(Enum):
    """Уровни логирования."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


# =============================================================================
# КЛАССЫ ДАННЫХ
# =============================================================================

@dataclass
class BotConfig:
    """Конфигурация бота, загружаемая из .env."""
    # БД
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "navigator"
    db_user: str = "postgres"
    db_password: str = ""
    
    # VK
    vk_token: str = ""
    
    # GigaChat
    gigachat_client_id: str = ""
    gigachat_client_secret: str = ""
    
    # Админы (список VK ID через запятую в .env)
    admin_ids: List[int] = field(default_factory=list)
    
    # Настройки
    log_level: str = "INFO"
    log_file: str = "navigator_bot.log"
    enable_gigachat: bool = True
    enable_antispam: bool = True
    max_history: int = MAX_HISTORY_MESSAGES
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Загружает конфигурацию из .env файла."""
        load_dotenv()
        
        config = cls()
        
        # БД
        config.db_host = os.getenv("DB_HOST", "localhost")
        config.db_port = int(os.getenv("DB_PORT", "5432"))
        config.db_name = os.getenv("DB_NAME", "navigator")
        config.db_user = os.getenv("DB_USER", "postgres")
        
        # Пароль — отдельная обработка (проблема с кодировкой)
        raw_password = os.getenv("DB_PASSWORD", "")
        if raw_password:
            try:
                config.db_password = raw_password.encode('utf-8', errors='replace').decode('utf-8')
            except Exception:
                config.db_password = str(raw_password)
        else:
            config.db_password = ""
        
        # VK
        config.vk_token = os.getenv("VK_TOKEN", "")
        
        # GigaChat
        config.gigachat_client_id = os.getenv("GIGACHAT_CLIENT_ID", "")
        config.gigachat_client_secret = os.getenv("GIGACHAT_CLIENT_SECRET", "")
        
        # Админы
        admin_ids_str = os.getenv("ADMIN_VK_IDS", "")
        if admin_ids_str:
            try:
                config.admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
            except ValueError:
                config.admin_ids = []
        
        # Настройки
        config.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        config.log_file = os.getenv("LOG_FILE", "navigator_bot.log")
        config.enable_gigachat = os.getenv("ENABLE_GIGACHAT", "true").lower() == "true"
        config.enable_antispam = os.getenv("ENABLE_ANTISPAM", "true").lower() == "true"
        
        try:
            config.max_history = int(os.getenv("MAX_HISTORY", str(MAX_HISTORY_MESSAGES)))
        except ValueError:
            config.max_history = MAX_HISTORY_MESSAGES
        
        return config
    
    def validate(self) -> List[str]:
        """Проверяет конфигурацию и возвращает список ошибок."""
        errors = []
        
        if not self.db_host:
            errors.append("DB_HOST не указан")
        if not self.db_name:
            errors.append("DB_NAME не указан")
        if not self.db_user:
            errors.append("DB_USER не указан")
        if not self.db_password:
            errors.append("DB_PASSWORD не указан")
        if not self.vk_token:
            errors.append("VK_TOKEN не указан")
        if not self.vk_token.startswith("vk"):
            errors.append("VK_TOKEN выглядит неверно (должен начинаться с 'vk')")
        if self.enable_gigachat:
            if not self.gigachat_client_id:
                errors.append("GIGACHAT_CLIENT_ID не указан, но GigaChat включён")
            if not self.gigachat_client_secret:
                errors.append("GIGACHAT_CLIENT_SECRET не указан, но GigaChat включён")
        
        return errors


@dataclass
class UserInfo:
    """Информация о пользователе."""
    vk_id: int = 0
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = UserRole.USER.value
    status: str = UserStatus.ACTIVE.value
    messages_count: int = 0
    first_seen: Optional[datetime.datetime] = None
    last_seen: Optional[datetime.datetime] = None
    is_admin: bool = False
    
    def full_name(self) -> str:
        """Возвращает полное имя пользователя."""
        parts = [p for p in [self.first_name, self.last_name] if p]
        if parts:
            return " ".join(parts)
        return self.username or f"ID:{self.vk_id}"


@dataclass
class MessageHistory:
    """Элемент истории сообщений."""
    id: int = 0
    vk_id: int = 0
    role: str = ""
    content: str = ""
    created_at: Optional[datetime.datetime] = None


@dataclass
class BotStats:
    """Статистика работы бота."""
    start_time: Optional[datetime.datetime] = None
    total_messages_received: int = 0
    total_messages_sent: int = 0
    total_users: int = 0
    total_gigachat_calls: int = 0
    total_errors: int = 0
    total_api_retries: int = 0
    total_spam_blocked: int = 0
    last_error: str = ""
    last_error_time: Optional[datetime.datetime] = None
    
    def uptime_str(self) -> str:
        """Возвращает строку времени работы."""
        if not self.start_time:
            return "не запущен"
        delta = datetime.datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}ч {minutes}м {seconds}с"


@dataclass
class AntispamEntry:
    """Запись для анти-спам системы."""
    messages: List[float] = field(default_factory=list)
    banned_until: float = 0.0


# =============================================================================
# СИСТЕМА ЛОГИРОВАНИЯ
# =============================================================================

class BotLogger:
    """Расширенная система логирования с ротацией файлов."""
    
    _instance: Optional["BotLogger"] = None
    _logger: Optional[logging.Logger] = None
    
    def __init__(self, log_file: str = "navigator_bot.log", level: str = "INFO"):
        self._setup_logger(log_file, level)
    
    def _setup_logger(self, log_file: str, level: str):
        """Настраивает логгер с файлом и консолью."""
        self._logger = logging.getLogger("navigator")
        self._logger.setLevel(getattr(logging, level, logging.INFO))
        
        # Очищаем старые хендлеры
        self._logger.handlers.clear()
        
        # Формат логов
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Файловый хендлер с ротацией (5 файлов по 5 МБ)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)
        
        # Консольный хендлер
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)
    
    @classmethod
    def get(cls) -> "BotLogger":
        """Возвращает singleton-экземпляр логгера."""
        if cls._instance is None:
            raise RuntimeError("BotLogger не инициализирован! Вызовите setup() сначала.")
        return cls._instance
    
    @classmethod
    def setup(cls, log_file: str, level: str):
        """Инициализация логгера."""
        cls._instance = BotLogger(log_file, level)
    
    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        self._logger.exception(msg, *args, **kwargs)


def get_logger() -> BotLogger:
    """Удобная функция для получения логгера."""
    return BotLogger.get()


# =============================================================================
# МЕНЕДЖЕР БАЗЫ ДАННЫХ
# =============================================================================

class DatabaseManager:
    """
    Менеджер базы данных с пулом соединений.
    Обеспечивает потокобезопасный доступ к PostgreSQL.
    """
    
    _instance: Optional["DatabaseManager"] = None
    
    def __init__(self, config: BotConfig):
        self.config = config
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._lock = threading.Lock()
        self._logger = get_logger()
        self._connected = False
    
    @classmethod
    def get_instance(cls, config: BotConfig) -> "DatabaseManager":
        """Создаёт или возвращает singleton-экземпляр."""
        if cls._instance is None:
            cls._instance = DatabaseManager(config)
        return cls._instance
    
    def connect(self) -> bool:
        """Создаёт пул соединений к БД."""
        try:
            self._logger.info(f"Подключение к БД: {self.config.db_host}:{self.config.db_port}/{self.config.db_name}")
            
            # Решение проблемы кодировки: явное указание кодировки
            self._pool = pool.ThreadedConnectionPool(
                minconn=DB_MIN_CONNECTIONS,
                maxconn=DB_MAX_CONNECTIONS,
                host=self.config.db_host,
                port=self.config.db_port,
                dbname=self.config.db_name,
                user=self.config.db_user,
                password=self.config.db_password,
                connect_timeout=DB_CONNECTION_TIMEOUT,
                options="-c client_encoding=UTF8",
                cursor_factory=RealDictCursor
            )
            
            # Тестовое подключение
            conn = self._pool.getconn()
            cur = conn.cursor()
            cur.execute("SELECT version();")
            version = cur.fetchone()
            self._pool.putconn(conn)
            
            self._connected = True
            self._logger.info(f"✅ БД подключена: {version['version'][:60]}...")
            return True
            
        except pg_errors.OperationalError as e:
            self._logger.error(f"❌ Ошибка подключения к БД (OperationalError): {e}")
            self._connected = False
            return False
        except pg_errors.AuthenticationError as e:
            self._logger.error(f"❌ Ошибка аутентификации БД: {e}")
            self._connected = False
            return False
        except Exception as e:
            # Обработка ошибки кодировки
            error_str = str(e)
            if "utf-8" in error_str.lower() or "codec" in error_str.lower():
                self._logger.error(
                    "❌ Ошибка кодировки при подключении к БД! "
                    "Проверьте, что пароль в .env не содержит нестандартных символов. "
                    f"Детали: {e}"
                )
            else:
                self._logger.error(f"❌ Неожиданная ошибка БД: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Закрывает все соединения пула."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
        self._connected = False
        self._logger.info("БД отключена.")
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._pool is not None
    
    def _get_conn(self):
        """Получает соединение из пула."""
        if not self._pool:
            raise RuntimeError("Пул соединений не инициализирован!")
        return self._pool.getconn()
    
    def _put_conn(self, conn):
        """Возвращает соединение в пул."""
        if self._pool:
            self._pool.putconn(conn)
    
    def _safe_execute(self, query: str, params: tuple = None, fetch: str = "none") -> Any:
        """
        Безопасное выполнение запроса с автоматическим возвратом соединения.
        
        :param query: SQL-запрос
        :param params: параметры запроса
        :param fetch: "none", "one", "all"
        :return: результат или None
        """
        conn = None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(query, params or ())
            
            result = None
            if fetch == "one":
                result = cur.fetchone()
            elif fetch == "all":
                result = cur.fetchall()
            elif fetch == "rowcount":
                result = cur.rowcount
            
            conn.commit()
            cur.close()
            return result
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._logger.error(f"Ошибка SQL: {e}\nЗапрос: {query[:200]}")
            raise
        finally:
            if conn:
                self._put_conn(conn)
    
    # --- Методы для работы с таблицами ---
    
    def init_tables(self):
        """Создаёт все необходимые таблицы, если их нет."""
        self._logger.info("Проверка и создание таблиц БД...")
        
        # Таблица пользователей
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                vk_id BIGINT NOT NULL UNIQUE,
                username VARCHAR(255),
                first_name VARCHAR(255) DEFAULT '',
                last_name VARCHAR(255) DEFAULT '',
                role VARCHAR(50) DEFAULT 'user',
                status VARCHAR(50) DEFAULT 'active',
                messages_count INTEGER DEFAULT 0,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица истории сообщений
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS dialog_history (
                id SERIAL PRIMARY KEY,
                vk_id BIGINT NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_dialog_user FOREIGN KEY (vk_id) 
                    REFERENCES users(vk_id) ON DELETE CASCADE
            )
        """)
        
        # Таблица сессий (диалогов)
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                vk_id BIGINT NOT NULL UNIQUE,
                session_uuid VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_session_user FOREIGN KEY (vk_id) 
                    REFERENCES users(vk_id) ON DELETE CASCADE
            )
        """)
        
        # Таблица статистики бота
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                id SERIAL PRIMARY KEY,
                stat_key VARCHAR(100) NOT NULL,
                stat_value BIGINT DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица логов ошибок
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id SERIAL PRIMARY KEY,
                error_type VARCHAR(100),
                error_message TEXT,
                stack_trace TEXT,
                vk_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица заблокированных пользователей (анти-спам)
        self._safe_execute("""
            CREATE TABLE IF NOT EXISTS spam_bans (
                id SERIAL PRIMARY KEY,
                vk_id BIGINT NOT NULL,
                ban_reason VARCHAR(255),
                banned_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_ban_user FOREIGN KEY (vk_id) 
                    REFERENCES users(vk_id) ON DELETE CASCADE
            )
        """)
        
        # Индексы
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_users_vk_id ON users(vk_id)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_dialog_vk_id ON dialog_history(vk_id)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_dialog_created ON dialog_history(created_at)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_sessions_vk_id ON sessions(vk_id)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_stats_key ON bot_stats(stat_key)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_errors_vk_id ON error_logs(vk_id)")
        self._safe_execute("CREATE INDEX IF NOT EXISTS idx_bans_vk_id ON spam_bans(vk_id)")
        
        self._logger.info("✅ Все таблицы БД готовы.")
    
    # --- Методы для работы с пользователями ---
    
    def get_or_create_user(self, vk_id: int, username: str = "", 
                           first_name: str = "", last_name: str = "") -> UserInfo:
        """Получает или создаёт пользователя в БД."""
        # Сначала пробуем найти
        row = self._safe_execute(
            "SELECT * FROM users WHERE vk_id = %s",
            (vk_id,),
            fetch="one"
        )
        
        if row:
            # Обновляем last_seen и, возможно, имя
            update_fields = ["last_seen = CURRENT_TIMESTAMP"]
            update_params: list = []
            
            if first_name and row.get('first_name', '') != first_name:
                update_fields.append("first_name = %s")
                update_params.append(first_name)
            if last_name and row.get('last_name', '') != last_name:
                update_fields.append("last_name = %s")
                update_params.append(last_name)
            if username and row.get('username', '') != username:
                update_fields.append("username = %s")
                update_params.append(username)
            
            update_params.append(vk_id)
            self._safe_execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE vk_id = %s",
                tuple(update_params)
            )
            
            return self._row_to_user(row)
        
        # Создаём нового
        self._safe_execute(
            """INSERT INTO users (vk_id, username, first_name, last_name) 
               VALUES (%s, %s, %s, %s)""",
            (vk_id, username, first_name, last_name)
        )
        
        # Получаем обратно
        row = self._safe_execute(
            "SELECT * FROM users WHERE vk_id = %s",
            (vk_id,),
            fetch="one"
        )
        self._logger.info(f"Новый пользователь: {vk_id} ({first_name} {last_name})")
        return self._row_to_user(row)
    
    def _row_to_user(self, row: Optional[Dict]) -> UserInfo:
        """Преобразует строку БД в объект UserInfo."""
        if not row:
            return UserInfo()
        return UserInfo(
            vk_id=row.get('vk_id', 0),
            username=row.get('username', ''),
            first_name=row.get('first_name', ''),
            last_name=row.get('last_name', ''),
            role=row.get('role', UserRole.USER.value),
            status=row.get('status', UserStatus.ACTIVE.value),
            messages_count=row.get('messages_count', 0),
            first_seen=row.get('first_seen'),
            last_seen=row.get('last_seen'),
        )
    
    def increment_user_messages(self, vk_id: int):
        """Увеличивает счётчик сообщений пользователя."""
        self._safe_execute(
            "UPDATE users SET messages_count = messages_count + 1, last_seen = CURRENT_TIMESTAMP WHERE vk_id = %s",
            (vk_id,)
        )
    
    def update_user_role(self, vk_id: int, role: str):
        """Обновляет роль пользователя."""
        self._safe_execute(
            "UPDATE users SET role = %s WHERE vk_id = %s",
            (role, vk_id)
        )
    
    def update_user_status(self, vk_id: int, status: str):
        """Обновляет статус пользователя."""
        self._safe_execute(
            "UPDATE users SET status = %s WHERE vk_id = %s",
            (status, vk_id)
        )
    
    def get_user(self, vk_id: int) -> Optional[UserInfo]:
        """Получает пользователя по VK ID."""
        row = self._safe_execute(
            "SELECT * FROM users WHERE vk_id = %s",
            (vk_id,),
            fetch="one"
        )
        return self._row_to_user(row) if row else None
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[UserInfo]:
        """Возвращает список всех пользователей."""
        rows = self._safe_execute(
            "SELECT * FROM users ORDER BY first_seen DESC LIMIT %s OFFSET %s",
            (limit, offset),
            fetch="all"
        )
        return [self._row_to_user(r) for r in rows] if rows else []
    
    def get_top_users(self, limit: int = 10) -> List[UserInfo]:
        """Возвращает топ активных пользователей."""
        rows = self._safe_execute(
            "SELECT * FROM users WHERE status = 'active' ORDER BY messages_count DESC LIMIT %s",
            (limit,),
            fetch="all"
        )
        return [self._row_to_user(r) for r in rows] if rows else []
    
    def get_total_users(self) -> int:
        """Возвращает общее количество пользователей."""
        row = self._safe_execute("SELECT COUNT(*) as cnt FROM users", fetch="one")
        return row['cnt'] if row else 0
    
    def delete_user(self, vk_id: int):
        """Удаляет пользователя и все его данные (каскадно)."""
        self._safe_execute("DELETE FROM users WHERE vk_id = %s", (vk_id,))
    
    # --- Методы для истории диалогов ---
    
    def add_message(self, vk_id: int, role: str, content: str):
        """Добавляет сообщение в историю диалога."""
        self._safe_execute(
            "INSERT INTO dialog_history (vk_id, role, content) VALUES (%s, %s, %s)",
            (vk_id, role, content[:5000])  # Ограничение длины
        )
    
    def get_history(self, vk_id: int, limit: int = MAX_HISTORY_MESSAGES) -> List[MessageHistory]:
        """Возвращает историю диалога пользователя."""
        rows = self._safe_execute(
            """SELECT * FROM dialog_history 
               WHERE vk_id = %s 
               ORDER BY created_at DESC LIMIT %s""",
            (vk_id, limit),
            fetch="all"
        )
        if not rows:
            return []
        # Разворачиваем в хронологическом порядке
        rows = list(reversed(rows))
        return [
            MessageHistory(
                id=r['id'],
                vk_id=r['vk_id'],
                role=r['role'],
                content=r['content'],
                created_at=r['created_at']
            )
            for r in rows
        ]
    
    def clear_history(self, vk_id: int) -> int:
        """Очищает историю диалога пользователя. Возвращает количество удалённых."""
        result = self._safe_execute(
            "DELETE FROM dialog_history WHERE vk_id = %s",
            (vk_id,),
            fetch="rowcount"
        )
        return result or 0
    
    def get_history_count(self, vk_id: int) -> int:
        """Возвращает количество сообщений в истории пользователя."""
        row = self._safe_execute(
            "SELECT COUNT(*) as cnt FROM dialog_history WHERE vk_id = %s",
            (vk_id,),
            fetch="one"
        )
        return row['cnt'] if row else 0
    
    # --- Методы для сессий ---
    
    def get_or_create_session(self, vk_id: int) -> str:
        """Создаёт или получает UUID сессии для пользователя."""
        row = self._safe_execute(
            "SELECT session_uuid FROM sessions WHERE vk_id = %s AND is_active = TRUE",
            (vk_id,),
            fetch="one"
        )
        if row and row['session_uuid']:
            return row['session_uuid']
        
        # Создаём новую сессию
        session_uuid = hashlib.md5(f"{vk_id}_{time.time()}_{random.randint(0, 999999)}".encode()).hexdigest()
        self._safe_execute(
            """INSERT INTO sessions (vk_id, session_uuid, is_active) 
               VALUES (%s, %s, TRUE)
               ON CONFLICT (vk_id) DO UPDATE SET session_uuid = EXCLUDED.session_uuid, is_active = TRUE, updated_at = CURRENT_TIMESTAMP""",
            (vk_id, session_uuid)
        )
        return session_uuid
    
    def deactivate_session(self, vk_id: int):
        """Деактивирует сессию пользователя."""
        self._safe_execute(
            "UPDATE sessions SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE vk_id = %s",
            (vk_id,)
        )
    
    # --- Методы для статистики ---
    
    def get_stat(self, key: str) -> int:
        """Получает значение статистики по ключу."""
        row = self._safe_execute(
            "SELECT stat_value FROM bot_stats WHERE stat_key = %s",
            (key,),
            fetch="one"
        )
        return row['stat_value'] if row else 0
    
    def set_stat(self, key: str, value: int):
        """Устанавливает значение статистики."""
        self._safe_execute(
            """INSERT INTO bot_stats (stat_key, stat_value, updated_at) 
               VALUES (%s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT DO NOTHING""",
            (key, value)
        )
        self._safe_execute(
            "UPDATE bot_stats SET stat_value = %s, updated_at = CURRENT_TIMESTAMP WHERE stat_key = %s",
            (value, key)
        )
    
    def increment_stat(self, key: str, by: int = 1):
        """Увеличивает значение статистики."""
        self._safe_execute(
            """INSERT INTO bot_stats (stat_key, stat_value, updated_at) 
               VALUES (%s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT DO NOTHING""",
            (key, 0)
        )
        self._safe_execute(
            "UPDATE bot_stats SET stat_value = stat_value + %s, updated_at = CURRENT_TIMESTAMP WHERE stat_key = %s",
            (by, key)
        )
    
    # --- Методы для логов ошибок ---
    
    def log_error(self, error_type: str, error_message: str, 
                  stack_trace: str = "", vk_id: int = 0):
        """Записывает ошибку в БД."""
        try:
            self._safe_execute(
                """INSERT INTO error_logs (error_type, error_message, stack_trace, vk_id) 
                   VALUES (%s, %s, %s, %s)""",
                (error_type, error_message[:500], stack_trace[:2000], vk_id)
            )
        except Exception as e:
            # Если не удалось записать ошибку в БД, логируем в файл
            get_logger().error(f"Не удалось записать ошибку в БД: {e}")
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict]:
        """Возвращает последние ошибки из БД."""
        rows = self._safe_execute(
            "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT %s",
            (limit,),
            fetch="all"
        )
        return rows if rows else []
    
    # --- Методы для анти-спама ---
    
    def ban_user_spam(self, vk_id: int, reason: str, duration: int = ANTISPAM_BAN_DURATION):
        """Банит пользователя за спам."""
        ban_until = datetime.datetime.now() + datetime.timedelta(seconds=duration)
        self._safe_execute(
            """INSERT INTO spam_bans (vk_id, ban_reason, banned_until) 
               VALUES (%s, %s, %s)""",
            (vk_id, reason, ban_until)
        )
        self.update_user_status(vk_id, UserStatus.BANNED.value)
    
    def unban_user_spam(self, vk_id: int):
        """Разбанивает пользователя."""
        self._safe_execute(
            "DELETE FROM spam_bans WHERE vk_id = %s",
            (vk_id,)
        )
        self.update_user_status(vk_id, UserStatus.ACTIVE.value)
    
    def is_user_banned(self, vk_id: int) -> bool:
        """Проверяет, забанен ли пользователь."""
        row = self._safe_execute(
            "SELECT banned_until FROM spam_bans WHERE vk_id = %s AND banned_until > NOW()",
            (vk_id,),
            fetch="one"
        )
        return row is not None
    
    def clean_expired_bans(self):
        """Удаляет истекшие баны."""
        self._safe_execute("DELETE FROM spam_bans WHERE banned_until < NOW()")
    
    # --- Резервное копирование ---
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """Возвращает сводную статистику БД."""
        result = {}
        
        result['total_users'] = self.get_total_users()
        result['active_users'] = self._safe_execute(
            "SELECT COUNT(*) as cnt FROM users WHERE status = 'active'",
            fetch="one"
        )['cnt'] if self._safe_execute(
            "SELECT COUNT(*) as cnt FROM users WHERE status = 'active'",
            fetch="one"
        ) else 0
        
        msg_row = self._safe_execute("SELECT COUNT(*) as cnt FROM dialog_history", fetch="one")
        result['total_messages'] = msg_row['cnt'] if msg_row else 0
        
        result['total_sessions'] = self._safe_execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE is_active = TRUE",
            fetch="one"
        )['cnt'] if self._safe_execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE is_active = TRUE",
            fetch="one"
        ) else 0
        
        return result


# =============================================================================
# МЕНЕДЖЕР VK API
# =============================================================================

class VKManager:
    """
    Менеджер VK API с обработкой ошибок, ретраями и корректным парсингом ответов.
    """
    
    def __init__(self, config: BotConfig):
        self.config = config
        self._logger = get_logger()
        self._vk_session: Optional[vk_api.VkApi] = None
        self._vk: Optional[Any] = None
        self._vk_longpoll: Optional[Any] = None
        self._group_id: int = 0
        self._group_name: str = ""
        self._connected = False
    
    def connect(self) -> bool:
        """Подключается к VK API и проверяет токен."""
        try:
            self._logger.info("Подключение к VK API...")
            
            if not self.config.vk_token:
                self._logger.error("VK_TOKEN пуст!")
                return False
            
            self._vk_session = vk_api.VkApi(token=self.config.vk_token, api_version=VK_API_VERSION)
            self._vk = self._vk_session.get_api()
            
            # Получаем информацию о группе
            # ВАЖНО: VK возвращает СПИСОК, даже если группа одна!
            groups_info = self._vk.groups.getById()
            
            if isinstance(groups_info, list):
                if len(groups_info) > 0:
                    group = groups_info[0]
                    self._group_id = group.get('id', 0)
                    self._group_name = group.get('name', 'Без названия')
                else:
                    self._logger.error("Список групп пуст! Возможно, токен не от сообщества.")
                    return False
            elif isinstance(groups_info, dict):
                # Иногда VK возвращает словарь с ключом 'groups'
                if 'groups' in groups_info and isinstance(groups_info['groups'], list):
                    if len(groups_info['groups']) > 0:
                        group = groups_info['groups'][0]
                        self._group_id = group.get('id', 0)
                        self._group_name = group.get('name', 'Без названия')
                    else:
                        self._logger.error("Список групп в ответе пуст!")
                        return False
                else:
                    self._group_id = groups_info.get('id', 0)
                    self._group_name = groups_info.get('name', 'Без названия')
            else:
                self._logger.error(f"Неожиданный формат ответа VK: {type(groups_info)}")
                return False
            
            if not self._group_id:
                self._logger.error("Не удалось получить ID группы!")
                return False
            
            self._connected = True
            self._logger.info(f"✅ VK API: группа «{self._group_name}» (ID: {self._group_id})")
            return True
            
        except ApiError as e:
            self._logger.error(f"❌ Ошибка VK API: {e}")
            return False
        except Exception as e:
            self._logger.error(f"❌ Критическая ошибка VK: {e}")
            self._logger.debug(traceback.format_exc())
            return False
    
    def init_longpoll(self) -> bool:
        """Инициализирует Long Polling для получения сообщений."""
        try:
            from vk_api.bot_longpoll import VkBotLongPoll, VkBotLongPollMode
            self._vk_longpoll = VkBotLongPoll(
                self._vk_session,
                self._group_id,
                wait=VK_LONG_POLL_WAIT,
                mode=VkBotLongPollMode.GET_EVENT_LISTENERS if hasattr(VkBotLongPollMode, 'GET_EVENT_LISTENERS') else VK_LONG_POLL_MODE
            )
            self._logger.info("✅ Long Polling инициализирован.")
            return True
        except ImportError:
            self._logger.warning("VkBotLongPoll недоступен. Используем ручной Long Polling.")
            return self._init_manual_longpoll()
        except Exception as e:
            self._logger.error(f"Ошибка инициализации Long Polling: {e}")
            return self._init_manual_longpoll()
    
    def _init_manual_longpoll(self) -> bool:
        """Ручная инициализация Long Polling через API."""
        try:
            # Получаем сервер для Long Polling
            server_info = self._vk.groups.getLongPollServer(group_id=self._group_id)
            self._lp_server = server_info.get('server', '')
            self._lp_key = server_info.get('key', '')
            self._lp_ts = server_info.get('ts', '')
            
            if not self._lp_server or not self._lp_key:
                self._logger.error("Не удалось получить данные Long Polling сервера!")
                return False
            
            self._logger.info("✅ Ручной Long Polling инициализирован.")
            return True
        except Exception as e:
            self._logger.error(f"Ошибка ручного Long Polling: {e}")
            return False
    
    def get_longpoll_events(self) -> List[Dict]:
        """
        Получает события через ручной Long Polling.
        Возвращает список событий.
        """
        try:
            if self._vk_longpoll:
                # Используем библиотечный Long Polling
                # Этот метод вызывается из run() — не используется напрямую
                return []
            
            url = self._lp_server
            params = {
                'act': 'a_check',
                'key': self._lp_key,
                'ts': self._lp_ts,
                'wait': VK_LONG_POLL_WAIT,
                'mode': VK_LONG_POLL_MODE,
                'version': VK_LONG_POLL_VERSION
            }
            
            response = requests.get(url, params=params, timeout=VK_LONG_POLL_WAIT + 5)
            data = response.json()
            
            if 'failed' in data:
                error_code = data['failed']
                if error_code == 1:
                    # История устарела — обновляем ts
                    self._lp_ts = data.get('ts', self._lp_ts)
                    return []
                elif error_code == 2:
                    # Ключ устарел — получаем новый
                    self._init_manual_longpoll()
                    return []
                elif error_code == 3:
                    # Информация утрачена — получаем новый сервер
                    self._init_manual_longpoll()
                    return []
                else:
                    self._logger.warning(f"Long Polling вернул ошибку: {error_code}")
                    return []
            
            self._lp_ts = data.get('ts', self._lp_ts)
            return data.get('events', [])
            
        except requests.Timeout:
            return []
        except Exception as e:
            self._logger.error(f"Ошибка получения событий Long Polling: {e}")
            return []
    
    def send_message(self, user_id: int, message: str, 
                     keyboard: Optional[str] = None,
                     reply_to: Optional[int] = None,
                     attachment: Optional[str] = None) -> bool:
        """
        Отправляет сообщение пользователю с повторными попытками.
        
        :param user_id: VK ID получателя
        :param message: текст сообщения
        :param keyboard: JSON клавиатуры
        :param reply_to: ID сообщения для ответа
        :param attachment: строка вложений
        :return: True если успешно
        """
        if not self._vk:
            self._logger.error("VK API не инициализирован!")
            return False
        
        # Разбиваем длинные сообщения
        messages = self._split_message(message)
        
        for i, msg_part in enumerate(messages):
            success = False
            for attempt in range(MAX_RETRIES_VK):
                try:
                    params = {
                        'user_id': user_id,
                        'message': msg_part,
                        'random_id': random.randint(0, 2**31 - 1),
                    }
                    if keyboard:
                        params['keyboard'] = keyboard
                    if reply_to and i == 0:
                        params['reply_to'] = reply_to
                    if attachment:
                        params['attachment'] = attachment
                    
                    self._vk.messages.send(**params)
                    success = True
                    break
                    
                except ApiError as e:
                    error_code = getattr(e, 'code', 0)
                    if error_code == 900:  # Нельзя отправить сообщение пользователю
                        self._logger.warning(f"Нельзя отправить сообщение пользователю {user_id}: {e}")
                        return False
                    elif error_code == 901:  # Пользователь запретил сообщения
                        self._logger.info(f"Пользователь {user_id} запретил сообщения")
                        return False
                    elif error_code == 913:  # Слишком много сообщений
                        time.sleep(1)
                        continue
                    elif error_code == 6:  # Слишком много запросов
                        time.sleep(0.5)
                        continue
                    else:
                        self._logger.error(f"Ошибка отправки (попытка {attempt+1}): {e}")
                        time.sleep(0.3 * (attempt + 1))
                except Exception as e:
                    self._logger.error(f"Неожиданная ошибка отправки: {e}")
                    time.sleep(0.3 * (attempt + 1))
            
            if not success:
                self._logger.error(f"Не удалось отправить сообщение юзеру {user_id} после {MAX_RETRIES_VK} попыток")
                return False
            
            time.sleep(VK_SEND_DELAY)
        
        return True
    
    def _split_message(self, message: str) -> List[str]:
        """Разбивает длинное сообщение на части (до MAX_MESSAGE_LENGTH символов)."""
        if len(message) <= MAX_MESSAGE_LENGTH:
            return [message]
        
        parts = []
        while len(message) > 0:
            if len(message) <= MAX_MESSAGE_LENGTH:
                parts.append(message)
                break
            
            # Ищем перенос строки для красивого разбиения
            split_pos = message.rfind('\n', 0, MAX_MESSAGE_LENGTH)
            if split_pos == -1:
                split_pos = message.rfind(' ', 0, MAX_MESSAGE_LENGTH)
            if split_pos == -1:
                split_pos = MAX_MESSAGE_LENGTH
            
            parts.append(message[:split_pos])
            message = message[split_pos:].lstrip()
        
        return parts
    
    def get_user_info(self, user_id: int) -> Dict[str, str]:
        """Получает информацию о пользователе из VK."""
        try:
            info = self._vk.users.get(user_ids=user_id, fields='first_name,last_name,screen_name')
            if isinstance(info, list) and len(info) > 0:
                user_data = info[0]
                return {
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                    'username': user_data.get('screen_name', ''),
                }
        except Exception as e:
            self._logger.warning(f"Не удалось получить инфо о пользователе {user_id}: {e}")
        return {}
    
    def send_typing(self, user_id: int):
        """Отправляет индикатор 'печатает...'."""
        try:
            self._vk.messages.setActivity(peer_id=user_id, type='typing')
        except Exception:
            pass  # Не критично
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def group_name(self) -> str:
        return self._group_name
    
    @property
    def group_id(self) -> int:
        return self._group_id


# =============================================================================
# МЕНЕДЖЕР GIGACHAT
# =============================================================================

class GigaChatManager:
    """
    Менеджер интеграции с GigaChat API.
    Поддерживает аутентификацию, повторные попытки и обработку ошибок.
    """
    
    def __init__(self, config: BotConfig):
        self.config = config
        self._logger = get_logger()
        self._access_token: Optional[str] = None
        self._token_expires: float = 0
        self._session = requests.Session()
        self._connected = False
        self._call_count = 0
        self._error_count = 0
    
    def authenticate(self) -> bool:
        """Получает access token для GigaChat API."""
        if not self.config.enable_gigachat:
            self._logger.info("GigaChat отключён в конфигурации.")
            return False
        
        if not self.config.gigachat_client_id or not self.config.gigachat_client_secret:
            self._logger.error("GigaChat: не указаны CLIENT_ID или CLIENT_SECRET!")
            return False
        
        try:
            self._logger.info("Аутентификация в GigaChat...")
            
            # Формируем Basic Auth из client_id:client_secret
            auth_string = f"{self.config.gigachat_client_id}:{self.config.gigachat_client_secret}"
            
            response = requests.post(
                f"{GIGACHAT_AUTH_URL}/oauth",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {self._base64_encode(auth_string)}"
                },
                data={"scope": "GIGACHAT_API_PERS"},
                timeout=30,
                verify=False  # Для тестового API
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data.get("access_token", "")
                # Токен обычно действителен ~30 минут
                expires_in = token_data.get("expires_in", 1800)
                self._token_expires = time.time() + expires_in - 60  # Запас 60 сек
                self._connected = True
                self._logger.info("✅ GigaChat: аутентификация успешна.")
                return True
            else:
                self._logger.error(f"GigaChat: ошибка аутентификации (HTTP {response.status_code}): {response.text[:200]}")
                self._connected = False
                return False
                
        except requests.exceptions.SSLError as e:
            self._logger.error(f"GigaChat: SSL ошибка: {e}")
            self._connected = False
            return False
        except requests.exceptions.ConnectionError as e:
            self._logger.error(f"GigaChat: ошибка соединения: {e}")
            self._connected = False
            return False
        except Exception as e:
            self._logger.error(f"GigaChat: неожиданная ошибка аутентификации: {e}")
            self._logger.debug(traceback.format_exc())
            self._connected = False
            return False
    
    def _base64_encode(self, text: str) -> str:
        """Кодирует строку в Base64."""
        import base64
        return base64.b64encode(text.encode('utf-8')).decode('utf-8')
    
    def _ensure_token(self) -> bool:
        """Проверяет валидность токена и обновляет при необходимости."""
        if not self._connected and not self.config.enable_gigachat:
            return False
        
        if self._access_token and time.time() < self._token_expires:
            return True
        
        # Токен истёк — обновляем
        return self.authenticate()
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, 
             max_tokens: int = 1000) -> Optional[str]:
        """
        Отправляет запрос к GigaChat и возвращает ответ.
        
        :param messages: список сообщений [{"role": "user", "content": "..."}]
        :param temperature: креативность (0-1)
        :param max_tokens: максимальная длина ответа
        :return: текст ответа или None при ошибке
        """
        if not self._ensure_token():
            self._logger.error("GigaChat: нет валидного токена!")
            return None
        
        # Добавляем системный промпт в начало, если его нет
        chat_messages = list(messages)
        if not chat_messages or chat_messages[0].get('role') != 'system':
            chat_messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        
        for attempt in range(GIGACHAT_MAX_RETRIES):
            try:
                response = requests.post(
                    f"{GIGACHAT_API_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": GIGACHAT_MODEL,
                        "messages": chat_messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=GIGACHAT_TIMEOUT,
                    verify=False
                )
                
                self._call_count += 1
                
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices and len(choices) > 0:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            return content.strip()
                    
                    self._logger.warning("GigaChat: пустой ответ в choices")
                    return None
                elif response.status_code == 401:
                    # Токен истёк — обновляем и повторяем
                    self._logger.warning("GigaChat: токен истёк, обновление...")
                    self.authenticate()
                    continue
                elif response.status_code == 429:
                    # Превышен лимит запросов
                    self._logger.warning(f"GigaChat: лимит запросов (попытка {attempt+1})")
                    time.sleep(GIGACHAT_RETRY_DELAY * (attempt + 1))
                    continue
                elif response.status_code == 400:
                    self._logger.error(f"GigaChat: неверный запрос: {response.text[:300]}")
                    return None
                else:
                    self._logger.error(f"GigaChat: HTTP {response.status_code}: {response.text[:300]}")
                    time.sleep(GIGACHAT_RETRY_DELAY * (attempt + 1))
                    
            except requests.Timeout:
                self._logger.warning(f"GigaChat: таймаут (попытка {attempt+1}/{GIGACHAT_MAX_RETRIES})")
                time.sleep(GIGACHAT_RETRY_DELAY)
            except requests.exceptions.ConnectionError as e:
                self._logger.error(f"GigaChat: ошибка соединения: {e}")
                time.sleep(GIGACHAT_RETRY_DELAY)
            except Exception as e:
                self._logger.error(f"GigaChat: неожиданная ошибка: {e}")
                self._logger.debug(traceback.format_exc())
                time.sleep(GIGACHAT_RETRY_DELAY)
        
        self._error_count += 1
        self._logger.error(f"GigaChat: все {GIGACHAT_MAX_RETRIES} попыток исчерпаны.")
        return None
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def call_count(self) -> int:
        return self._call_count
    
    @property
    def error_count(self) -> int:
        return self._error_count


# =============================================================================
# АНТИ-СПАМ СИСТЕМА
# =============================================================================

class AntispamSystem:
    """
    Система защиты от спама на основе временных окон.
    Отслеживает частоту сообщений от каждого пользователя.
    """
    
    def __init__(self, db: DatabaseManager, enabled: bool = True):
        self._db = db
        self._enabled = enabled
        self._logger = get_logger()
        self._entries: Dict[int, AntispamEntry] = {}
        self._lock = threading.Lock()
    
    def check(self, vk_id: int) -> Tuple[bool, str]:
        """
        Проверяет, не спамит ли пользователь.
        
        :return: (True если можно отправить, причина запрета если нет)
        """
        if not self._enabled:
            return True, ""
        
        # Сначала проверяем бан в БД
        if self._db.is_user_banned(vk_id):
            return False, "Вы временно заблокированы за спам. Попробуйте позже."
        
        now = time.time()
        
        with self._lock:
            entry = self._entries.get(vk_id)
            
            if entry is None:
                entry = AntispamEntry()
                self._entries[vk_id] = entry
            
            # Проверяем активный бан
            if entry.banned_until > now:
                remaining = int(entry.banned_until - now)
                return False, f"Анти-спам: подождите {remaining} сек."
            
            # Очищаем старые сообщения (вне окна)
            entry.messages = [t for t in entry.messages if now - t < ANTISPAM_WINDOW]
            
            # Добавляем текущее
            entry.messages.append(now)
            
            # Проверяем лимит
            if len(entry.messages) > ANTISPAM_MAX_MESSAGES:
                # Баним
                entry.banned_until = now + ANTISPAM_BAN_DURATION
                self._db.ban_user_spam(vk_id, f"Превышение лимита: {len(entry.messages)} сообщений за {ANTISPAM_WINDOW} сек.")
                self._logger.warning(f"Анти-спам: пользователь {vk_id} забанен на {ANTISPAM_BAN_DURATION} сек.")
                return False, f"⚠️ Слишком много сообщений! Вы заблокированы на {ANTISPAM_BAN_DURATION} секунд."
        
        return True, ""
    
    def reset(self, vk_id: int):
        """Сбрасывает счётчик для пользователя."""
        with self._lock:
            if vk_id in self._entries:
                self._entries[vk_id].messages.clear()
                self._entries[vk_id].banned_until = 0
    
    def unban(self, vk_id: int):
        """Разбанивает пользователя."""
        with self._lock:
            if vk_id in self._entries:
                self._entries[vk_id].banned_until = 0
                self._entries[vk_id].messages.clear()
        self._db.unban_user_spam(vk_id)


# =============================================================================
# ОБРАБОТЧИК КОМАНД
# =============================================================================

class CommandHandler:
    """
    Обработчик команд бота (начинаются с символа ADMIN_COMMAND_PREFIX).
    """
    
    def __init__(self, bot: "NavigatorBot"):
        self.bot = bot
        self._logger = get_logger()
        self._commands: Dict[str, Any] = {}
        self._admin_commands: Dict[str, Any] = {}
        self._register_commands()
    
    def _register_commands(self):
        """Регистрирует все команды."""
        # Пользовательские команды
        self._commands['help'] = self._cmd_help
        self._commands['h'] = self._cmd_help
        self._commands['stats'] = self._cmd_stats
        self._commands['clear'] = self._cmd_clear
        self._commands['about'] = self._cmd_about
        self._commands['top'] = self._cmd_top
        
        # Админ-команды
        self._admin_commands['users'] = self._admin_users
        self._admin_commands['broadcast'] = self._admin_broadcast
        self._admin_commands['ban'] = self._admin_ban
        self._admin_commands['unban'] = self._admin_unban
        self._admin_commands['health'] = self._admin_health
        self._admin_commands['shutdown'] = self._admin_shutdown
        self._admin_commands['errors'] = self._admin_errors
        self._admin_commands['dbstats'] = self._admin_dbstats
        self._admin_commands['promote'] = self._admin_promote
    
    def handle(self, user: UserInfo, text: str) -> Optional[str]:
        """
        Обрабатывает команду и возвращает ответ.
        Возвращает None, если текст не является командой.
        """
        text = text.strip()
        if not text.startswith(ADMIN_COMMAND_PREFIX):
            return None
        
        # Парсим команду
        parts = text[1:].split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""
        
        # Проверяем пользовательские команды
        if command in self._commands:
            return self._commands[command](user, args)
        
        # Проверяем админ-команды
        if command in self._admin_commands:
            if not user.is_admin:
                return "❌ У вас нет прав для этой команды."
            return self._admin_commands[command](user, args)
        
        return f"❓ Неизвестная команда. Введите !help для списка команд."
    
    # --- Пользовательские команды ---
    
    def _cmd_help(self, user: UserInfo, args: str) -> str:
        return HELP_MESSAGE
    
    def _cmd_stats(self, user: UserInfo, args: str) -> str:
        msg_count = self.bot.db.get_history_count(user.vk_id)
        history_msgs = self.bot.db.get_history(user.vk_id, 1)
        
        result = (
            f"📊 Ваша статистика:\n\n"
            f"Имя: {user.full_name()}\n"
            f"VK ID: {user.vk_id}\n"
            f"Сообщений отправлено: {user.messages_count}\n"
            f"Сообщений в истории: {msg_count}\n"
        )
        
        if user.first_seen:
            result += f"Регистрация: {user.first_seen.strftime('%Y-%m-%d %H:%M')}\n"
        if user.last_seen:
            result += f"Последняя активность: {user.last_seen.strftime('%Y-%m-%d %H:%M')}\n"
        
        result += f"Роль: {user.role}\n"
        result += f"Статус: {user.status}\n"
        
        return result
    
    def _cmd_clear(self, user: UserInfo, args: str) -> str:
        count = self.bot.db.clear_history(user.vk_id)
        self.bot.db.deactivate_session(user.vk_id)
        return f"🧹 История диалога очищена! Удалено сообщений: {count}"
    
    def _cmd_about(self, user: UserInfo, args: str) -> str:
        return ABOUT_MESSAGE
    
    def _cmd_top(self, user: UserInfo, args: str) -> str:
        top_users = self.bot.db.get_top_users(10)
        if not top_users:
            return "📊 Пока нет активных пользователей."
        
        lines = ["🏆 Топ активных пользователей:\n"]
        for i, u in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            lines.append(f"{medal} {u.full_name()} — {u.messages_count} сообщений")
        
        return "\n".join(lines)
    
    # --- Админ-команды ---
    
    def _admin_users(self, user: UserInfo, args: str) -> str:
        """Список пользователей."""
        try:
            limit = int(args) if args else 20
        except ValueError:
            limit = 20
        limit = min(limit, 100)
        
        users = self.bot.db.get_all_users(limit=limit)
        if not users:
            return "👥 Пользователей пока нет."
        
        lines = [f"👥 Последние {len(users)} пользователей:\n"]
        for u in users:
            status_icon = "✅" if u.status == "active" else "❌" if u.status == "banned" else "⏸"
            lines.append(f"{status_icon} {u.full_name()} (ID: {u.vk_id}) — {u.messages_count} сообщ.")
        
        total = self.bot.db.get_total_users()
        lines.append(f"\nВсего пользователей: {total}")
        return "\n".join(lines)
    
    def _admin_broadcast(self, user: UserInfo, args: str) -> str:
        """Рассылка всем пользователям."""
        if not args:
            return "Использование: !broadcast текст сообщения"
        
        all_users = self.bot.db.get_all_users(limit=10000)
        sent = 0
        failed = 0
        
        for u in all_users:
            if u.status == "active":
                if self.bot.vk.send_message(u.vk_id, f"📢 Рассылка:\n\n{args}"):
                    sent += 1
                else:
                    failed += 1
                time.sleep(0.05)  # Не спамим VK API
        
        return f"📢 Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}"
    
    def _admin_ban(self, user: UserInfo, args: str) -> str:
        """Бан пользователя по VK ID."""
        try:
            target_id = int(args.split()[0]) if args else 0
        except ValueError:
            return "Использование: !ban VK_ID"
        
        if not target_id:
            return "Использование: !ban VK_ID"
        
        self.bot.db.update_user_status(target_id, UserStatus.BANNED.value)
        self.bot.antispam.ban_user_spam(target_id, f"Забанен админом {user.vk_id}")
        return f"🚫 Пользователь {target_id} заблокирован."
    
    def _admin_unban(self, user: UserInfo, args: str) -> str:
        """Разбан пользователя."""
        try:
            target_id = int(args.split()[0]) if args else 0
        except ValueError:
            return "Использование: !unban VK_ID"
        
        if not target_id:
            return "Использование: !unban VK_ID"
        
        self.bot.db.update_user_status(target_id, UserStatus.ACTIVE.value)
        self.bot.antispam.unban(target_id)
        return f"✅ Пользователь {target_id} разблокирован."
    
    def _admin_health(self, user: UserInfo, args: str) -> str:
        """Проверка здоровья системы."""
        db_ok = self.bot.db.is_connected
        vk_ok = self.bot.vk.is_connected
        gc_ok = self.bot.gigachat.is_connected
        
        lines = ["🏥 Проверка здоровья системы:\n"]
        lines.append(f"БД PostgreSQL: {'✅ Работает' if db_ok else '❌ Оффлайн'}")
        lines.append(f"VK API: {'✅ Работает' if vk_ok else '❌ Оффлайн'}")
        lines.append(f"GigaChat: {'✅ Работает' if gc_ok else '❌ Оффлайн' if self.bot.config.enable_gigachat else '⏸ Отключён'}")
        lines.append(f"Бот работает: {self.bot.stats.uptime_str()}")
        lines.append(f"Состояние: {self.bot.state.name}")
        
        lines.append(f"\n--- Статистика ---")
        lines.append(f"Получено сообщений: {self.bot.stats.total_messages_received}")
        lines.append(f"Отправлено сообщений: {self.bot.stats.total_messages_sent}")
        lines.append(f"Вызовов GigaChat: {self.bot.gigachat.call_count}")
        lines.append(f"Ошибок GigaChat: {self.bot.gigachat.error_count}")
        lines.append(f"Заблокировано спама: {self.bot.stats.total_spam_blocked}")
        lines.append(f"Всего ошибок: {self.bot.stats.total_errors}")
        
        return "\n".join(lines)
    
    def _admin_shutdown(self, user: UserInfo, args: str) -> str:
        """Остановка бота."""
        self.bot.request_shutdown()
        return "👋 Бот останавливается..."
    
    def _admin_errors(self, user: UserInfo, args: str) -> str:
        """Последние ошибки из БД."""
        errors = self.bot.db.get_recent_errors(10)
        if not errors:
            return "✅ Ошибок в логе БД нет!"
        
        lines = ["📋 Последние ошибки:\n"]
        for err in errors:
            err_type = err.get('error_type', 'Unknown')
            err_msg = err.get('error_message', '')[:100]
            err_time = err.get('created_at', '')
            lines.append(f"[{err_time}] {err_type}: {err_msg}")
        
        return "\n".join(lines)
    
    def _admin_dbstats(self, user: UserInfo, args: str) -> str:
        """Статистика БД."""
        stats = self.bot.db.get_stats_summary()
        lines = ["📊 Статистика БД:\n"]
        lines.append(f"Всего пользователей: {stats.get('total_users', 0)}")
        lines.append(f"Активных пользователей: {stats.get('active_users', 0)}")
        lines.append(f"Всего сообщений: {stats.get('total_messages', 0)}")
        lines.append(f"Активных сессий: {stats.get('total_sessions', 0)}")
        return "\n".join(lines)
    
    def _admin_promote(self, user: UserInfo, args: str) -> str:
        """Повышение пользователя до админа."""
        try:
            target_id = int(args.split()[0]) if args else 0
        except ValueError:
            return "Использование: !promote VK_ID"
        
        if not target_id:
            return "Использование: !promote VK_ID"
        
        self.bot.db.update_user_role(target_id, UserRole.ADMIN.value)
        return f"⭐ Пользователь {target_id} повышен до админа."


# =============================================================================
# ГЛАВНЫЙ КЛАСС БОТА
# =============================================================================

class NavigatorBot:
    """
    Главный класс бота «Навигатор Успеха».
    Объединяет все компоненты и управляет жизненным циклом.
    """
    
    def __init__(self, config: BotConfig):
        self.config = config
        self._logger = get_logger()
        self._state = BotState.STOPPED
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()
        
        # Инициализация компонентов
        self.db: Optional[DatabaseManager] = None
        self.vk: Optional[VKManager] = None
        self.gigachat: Optional[GigaChatManager] = None
        self.antispam: Optional[AntispamSystem] = None
        self.command_handler: Optional[CommandHandler] = None
        
        # Статистика
        self.stats = BotStats()
        
        # Очередь сообщений
        self._message_queue: queue.Queue = queue.Queue(maxsize=1000)
        
        # Потоки
        self._poll_thread: Optional[threading.Thread] = None
        self._worker_threads: List[threading.Thread] = []
        self._health_thread: Optional[threading.Thread] = None
        self._stats_thread: Optional[threading.Thread] = None
    
    @property
    def state(self) -> BotState:
        return self._state
    
    # --- Инициализация ---
    
    def initialize(self) -> bool:
        """Инициализирует все компоненты бота."""
        self._state = BotState.STARTING
        self._logger.info(f"{'='*60}")
        self._logger.info(f"  {BOT_NAME} v{BOT_VERSION} — Запуск инициализации...")
        self._logger.info(f"{'='*60}")
        
        # Проверка конфигурации
        config_errors = self.config.validate()
        if config_errors:
            self._logger.error("Ошибки конфигурации:")
            for err in config_errors:
                self._logger.error(f"  - {err}")
            self._state = BotState.ERROR
            return False
        
        self._logger.info("✅ Конфигурация проверена.")
        
        # 1. Инициализация БД
        self.db = DatabaseManager.get_instance(self.config)
        if not self.db.connect():
            self._logger.error("Не удалось подключиться к БД!")
            self._state = BotState.ERROR
            return False
        
        # Создаём таблицы
        try:
            self.db.init_tables()
        except Exception as e:
            self._logger.error(f"Ошибка создания таблиц: {e}")
            self._state = BotState.ERROR
            return False
        
        # 2. Инициализация VK API
        self.vk = VKManager(self.config)
        if not self.vk.connect():
            self._logger.error("Не удалось подключиться к VK API!")
            self._state = BotState.ERROR
            return False
        
        if not self.vk.init_longpoll():
            self._logger.error("Не удалось инициализировать Long Polling!")
            self._state = BotState.ERROR
            return False
        
        # 3. Инициализация GigaChat
        self.gigachat = GigaChatManager(self.config)
        if self.config.enable_gigachat:
            if not self.gigachat.authenticate():
                self._logger.warning("GigaChat недоступен. Бот будет работать в режиме без ИИ.")
        else:
            self._logger.info("GigaChat отключён в конфигурации.")
        
        # 4. Инициализация анти-спама
        self.antispam = AntispamSystem(self.db, self.config.enable_antispam)
        
        # 5. Инициализация обработчика команд
        self.command_handler = CommandHandler(self)
        
        # 6. Загружаем статистику из БД
        self.stats.total_users = self.db.get_total_users()
        self._logger.info(f"Пользователей в БД: {self.stats.total_users}")
        
        # 7. Очистка истекших банов
        self.db.clean_expired_bans()
        
        self._logger.info(f"{'='*60}")
        self._logger.info(f"  {BOT_NAME} — Инициализация завершена!")
        self._logger.info(f"  Группа: «{self.vk.group_name}» (ID: {self.vk.group_id})")
        self._logger.info(f"  БД: {self.config.db_name}@{self.config.db_host}")
        self._logger.info(f"  GigaChat: {'Включён' if self.gigachat.is_connected else 'Отключён'}")
        self._logger.info(f"  Анти-спам: {'Включён' if self.config.enable_antispam else 'Отключён'}")
        self._logger.info(f"{'='*60}")
        
        return True
    
    # --- Запуск ---
    
    def start(self):
        """Запускает бота."""
        if not self.initialize():
            self._logger.error("Инициализация провалилась! Бот не запущен.")
            return
        
        self._state = BotState.RUNNING
        self.stats.start_time = datetime.datetime.now()
        
        self._logger.info(f"🚀 {BOT_NAME} запущен и готов к работе!")
        
        # Запуск потоков
        self._start_polling()
        self._start_workers()
        self._start_health_check()
        self._start_stats_dump()
        
        # Ждём сигнала остановки
        try:
            while not self._shutdown_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            self._logger.info("Получен сигнал прерывания (Ctrl+C)")
            self.request_shutdown()
        
        self._wait_for_threads()
        self._cleanup()
        
        self._logger.info(f"👋 {BOT_NAME} остановлен. Время работы: {self.stats.uptime_str()}")
    
    def _start_polling(self):
        """Запускает поток получения событий от VK."""
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="VK-Poller")
        self._poll_thread.start()
        self._logger.info("Поток polling запущен.")
    
    def _start_workers(self, num_workers: int = 3):
        """Запускает рабочие потоки для обработки сообщений."""
        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"Worker-{i+1}")
            t.start()
            self._worker_threads.append(t)
        self._logger.info(f"Запущено {num_workers} рабочих потоков.")
    
    def _start_health_check(self):
        """Запускает поток периодической проверки здоровья."""
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True, name="Health-Check")
        self._health_thread.start()
        self._logger.info("Поток health-check запущен.")
    
    def _start_stats_dump(self):
        """Запускает поток периодического дампа статистики."""
        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True, name="Stats-Dump")
        self._stats_thread.start()
        self._logger.info("Поток статистики запущен.")
    
    # --- Основные циклы ---
    
    def _poll_loop(self):
        """Цикл получения событий от VK Long Polling."""
        self._logger.info("Polling loop запущен.")
        
        while not self._shutdown_event.is_set():
            try:
                if self.vk._vk_longpoll:
                    # Используем библиотечный Long Polling
                    for event in self.vk._vk_longpoll.listen():
                        if self._shutdown_event.is_set():
                            break
                        self._process_vk_event(event)
                else:
                    # Ручной Long Polling
                    events = self.vk.get_longpoll_events()
                    for event in events:
                        if self._shutdown_event.is_set():
                            break
                        self._process_raw_event(event)
                    
                    if not events:
                        time.sleep(0.1)
                        
            except Exception as e:
                self._logger.error(f"Ошибка в poll loop: {e}")
                self._logger.debug(traceback.format_exc())
                time.sleep(1)
        
        self._logger.info("Polling loop остановлен.")
    
    def _process_vk_event(self, event):
        """Обрабатывает событие из библиотечного Long Polling."""
        try:
            # Проверяем, что это новое сообщение
            if hasattr(event, 'type') and event.type == vk_api.bot_longpoll.VkBotEventType.MESSAGE_NEW:
                msg_data = event.obj.get('message', event.obj)
                self._handle_incoming_message(msg_data)
        except Exception as e:
            self._logger.error(f"Ошибка обработки события VK: {e}")
    
    def _process_raw_event(self, event: Dict):
        """Обрабатывает событие из ручного Long Polling."""
        try:
            if event.get('type') == 'message_new':
                msg_data = event.get('object', {}).get('message', {})
                if msg_data:
                    self._handle_incoming_message(msg_data)
        except Exception as e:
            self._logger.error(f"Ошибка обработки raw-события: {e}")
    
    def _handle_incoming_message(self, msg_data: Dict):
        """Обрабатывает входящее сообщение и ставит его в очередь."""
        try:
            user_id = msg_data.get('from_id') or msg_data.get('user_id', 0)
            text = msg_data.get('text', '').strip()
            msg_id = msg_data.get('conversation_message_id') or msg_data.get('id', 0)
            
            if not user_id or not text:
                return
            
            # Помещаем в очередь
            try:
                self._message_queue.put_nowait({
                    'user_id': user_id,
                    'text': text,
                    'msg_id': msg_id,
                    'timestamp': time.time()
                })
            except queue.Full:
                self._logger.warning("Очередь сообщений переполнена! Пропускаю сообщение.")
                
        except Exception as e:
            self._logger.error(f"Ошибка помещения сообщения в очередь: {e}")
    
    def _worker_loop(self):
        """Цикл рабочего потока — берёт сообщения из очереди и обрабатывает."""
        thread_name = threading.current_thread().name
        self._logger.info(f"{thread_name}: запущен.")
        
        while not self._shutdown_event.is_set():
            try:
                msg_item = self._message_queue.get(timeout=1)
                if msg_item:
                    self._process_message(msg_item)
                    self._message_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self._logger.error(f"{thread_name}: ошибка обработки: {e}")
                self._logger.debug(traceback.format_exc())
        
        self._logger.info(f"{thread_name}: остановлен.")
    
    def _process_message(self, msg_item: Dict):
        """
        Основная обработка сообщения.
        Здесь происходит вся логика: регистрация, команды, GigaChat.
        """
        user_id = msg_item['user_id']
        text = msg_item['text']
        
        self.stats.total_messages_received += 1
        
        try:
            # 1. Получаем информацию о пользователе из VK
            vk_user_info = self.vk.get_user_info(user_id)
            
            # 2. Регистрируем/обновляем пользователя в БД
            user = self.db.get_or_create_user(
                vk_id=user_id,
                username=vk_user_info.get('username', ''),
                first_name=vk_user_info.get('first_name', ''),
                last_name=vk_user_info.get('last_name', '')
            )
            
            # Проверяем, является ли пользователь админом
            if user_id in self.config.admin_ids:
                user.is_admin = True
                if user.role != UserRole.ADMIN.value:
                    self.db.update_user_role(user_id, UserRole.ADMIN.value)
            
            # 3. Проверяем статус пользователя
            if user.status == UserStatus.BANNED.value:
                self.vk.send_message(user_id, "🚫 Вы заблокированы.")
                return
            
            # 4. Анти-спам проверка
            allowed, reason = self.antispam.check(user_id)
            if not allowed:
                self.stats.total_spam_blocked += 1
                self.vk.send_message(user_id, reason)
                return
            
            # 5. Обработка команд
            if text.startswith(ADMIN_COMMAND_PREFIX):
                response = self.command_handler.handle(user, text)
                if response:
                    self.vk.send_message(user_id, response)
                    self.stats.total_messages_sent += 1
                return
            
            # 6. Обычное сообщение — отправляем в GigaChat
            self._handle_chat_message(user, text)
            
        except Exception as e:
            self.stats.total_errors += 1
            self.stats.last_error = str(e)
            self.stats.last_error_time = datetime.datetime.now()
            self._logger.error(f"Ошибка обработки сообщения от {user_id}: {e}")
            self._logger.debug(traceback.format_exc())
            
            # Записываем ошибку в БД
            self.db.log_error(
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                vk_id=user_id
            )
            
            # Уведомляем пользователя
            try:
                self.vk.send_message(user_id, "😔 Произошла ошибка при обработке сообщения. Попробуйте позже.")
            except Exception:
                pass
    
    def _handle_chat_message(self, user: UserInfo, text: str):
        """Обрабатывает обычное сообщение через GigaChat."""
        # Увеличиваем счётчик сообщений
        self.db.increment_user_messages(user.vk_id)
        user.messages_count += 1
        
        # Сохраняем сообщение пользователя в историю
        self.db.add_message(user.vk_id, MessageType.USER.value, text)
        
        # Получаем сессию
        session_uuid = self.db.get_or_create_session(user.vk_id)
        
        # Проверяем, доступен ли GigaChat
        if not self.gigachat or not self.gigachat.is_connected:
            # Пытаемся переподключиться
            if self.config.enable_gigachat:
                self._logger.info("Попытка переподключения к GigaChat...")
                self.gigachat.authenticate()
            
            if not self.gigachat.is_connected:
                fallback = self._get_fallback_response(text)
                self.db.add_message(user.vk_id, MessageType.ASSISTANT.value, fallback)
                self.vk.send_message(user.vk_id, fallback)
                self.stats.total_messages_sent += 1
                return
        
        # Отправляем индикатор "печатает..."
        self.vk.send_typing(user.vk_id)
        
        # Получаем историю диалога
        history = self.db.get_history(user.vk_id, self.config.max_history)
        
        # Формируем сообщения для GigaChat
        chat_messages = []
        for msg in history:
            chat_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Отправляем запрос к GigaChat
        self._logger.debug(f"GigaChat запрос от {user.vk_id} ({len(chat_messages)} сообщений в контексте)")
        
        response_text = self.gigachat.chat(
            messages=chat_messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        if not response_text:
            response_text = self._get_fallback_response(text)
        
        # Сохраняем ответ в историю
        self.db.add_message(user.vk_id, MessageType.ASSISTANT.value, response_text)
        
        # Отправляем ответ пользователю
        if self.vk.send_message(user.vk_id, response_text):
            self.stats.total_messages_sent += 1
            self.stats.total_gigachat_calls += 1
        else:
            self._logger.error(f"Не удалось отправить ответ пользователю {user.vk_id}")
            self.stats.total_errors += 1
    
    def _get_fallback_response(self, text: str) -> str:
        """Возвращает запасной ответ, когда GigaChat недоступен."""
        fallbacks = [
            "К сожалению, сервис ИИ временно недоступен. Но я всё равно здесь! "
            "Попробуйте переформулировать вопрос или напишите позже. 🙏",
            
            "Сейчас я не могу подключиться к нейросети, но вот что я могу сказать: "
            "каждый шаг к цели важен, даже маленький. Что вы хотите обсудить? 💪",
            
            "ИИ-сервис на техническом перерыве. А пока — вот совет дня: "
            "начните с малого, но начните сегодня! 🚀",
            
            "Прошу прощения, нейросеть недоступна. Но вы можете использовать команды "
            "!help, !stats или !about, пока мы восстанавливаем работу. 🔧"
        ]
        return random.choice(fallbacks)
    
    # --- Health check и статистика ---
    
    def _health_loop(self):
        """Периодическая проверка здоровья системы."""
        while not self._shutdown_event.is_set():
            try:
                self._shutdown_event.wait(HEALTH_CHECK_INTERVAL)
                if self._shutdown_event.is_set():
                    break
                
                # Проверяем БД
                if not self.db.is_connected:
                    self._logger.warning("Health: БД отключена, попытка переподключения...")
                    self.db.connect()
                    if self.db.is_connected:
                        self.db.init_tables()
                
                # Проверяем GigaChat
                if self.config.enable_gigachat and self.gigachat:
                    if not self.gigachat.is_connected:
                        self._logger.warning("Health: GigaChat отключен, попытка переподключения...")
                        self.gigachat.authenticate()
                
                # Очищаем истёкшие баны
                self.db.clean_expired_bans()
                
                self._logger.info(
                    f"Health: OK | БД:{'✅' if self.db.is_connected else '❌'} | "
                    f"VK:{'✅' if self.vk.is_connected else '❌'} | "
                    f"GC:{'✅' if self.gigachat.is_connected else '❌'} | "
                    f"Uptime: {self.stats.uptime_str()}"
                )
                
            except Exception as e:
                self._logger.error(f"Health check ошибка: {e}")
    
    def _stats_loop(self):
        """Периодический дамп статистики в БД."""
        while not self._shutdown_event.is_set():
            try:
                self._shutdown_event.wait(STATS_DUMP_INTERVAL)
                if self._shutdown_event.is_set():
                    break
                
                self.db.increment_stat('total_messages_received', self.stats.total_messages_received)
                self.db.increment_stat('total_messages_sent', self.stats.total_messages_sent)
                self.db.increment_stat('total_gigachat_calls', self.stats.total_gigachat_calls)
                self.db.increment_stat('total_errors', self.stats.total_errors)
                self.db.increment_stat('total_spam_blocked', self.stats.total_spam_blocked)
                
                self._logger.info(
                    f"Stats dump: msg_in={self.stats.total_messages_received}, "
                    f"msg_out={self.stats.total_messages_sent}, "
                    f"gc_calls={self.stats.total_gigachat_calls}, "
                    f"errors={self.stats.total_errors}"
                )
                
            except Exception as e:
                self._logger.error(f"Stats dump ошибка: {e}")
    
    # --- Управление жизненным циклом ---
    
    def request_shutdown(self):
        """Запрашивает остановку бота."""
        self._logger.info("Получен запрос на остановку...")
        self._state = BotState.STOPPING
        self._shutdown_event.set()
    
    def _wait_for_threads(self):
        """Ждёт завершения всех потоков."""
        self._logger.info("Ожидание завершения потоков...")
        
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)
        
        for t in self._worker_threads:
            if t.is_alive():
                t.join(timeout=5)
        
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=2)
        
        if self._stats_thread and self._stats_thread.is_alive():
            self._stats_thread.join(timeout=2)
    
    def _cleanup(self):
        """Очищает ресурсы при завершении."""
        self._logger.info("Очистка ресурсов...")
        
        if self.db:
            self.db.disconnect()
        
        # Отключаем предупреждения requests
        import warnings
        warnings.filterwarnings("ignore")
        
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        
        self._state = BotState.STOPPED


# =============================================================================
# СИГНАЛЫ ОС
# =============================================================================

_bot_instance: Optional[NavigatorBot] = None

def _signal_handler(signum, frame):
    """Обработчик сигналов ОС для корректного завершения."""
    global _bot_instance
    if _bot_instance:
        get_logger().info(f"Получен сигнал {signum}, остановка бота...")
        _bot_instance.request_shutdown()


def _setup_signal_handlers(bot: NavigatorBot):
    """Устанавливает обработчики сигналов."""
    global _bot_instance
    _bot_instance = bot
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


# =============================================================================
# ФУНКЦИЯ БАННЕРА
# =============================================================================

def print_banner():
    """Выводит баннер в консоль при запуске."""
    banner = r"""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║     ★  Н А В И Г А Т О Р   У С П Е Х А  ★               ║
    ║                                                          ║
    ║     VK-бот с интеграцией GigaChat                        ║
    ║     Версия 2.0.0                                         ║
    ║     LifeCode Studio                                      ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)


# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Главная функция — точка входа."""
    print_banner()
    
    # Загрузка конфигурации
    config = BotConfig.from_env()
    
    # Инициализация логгера
    BotLogger.setup(config.log_file, config.log_level)
    logger = get_logger()
    
    logger.info("=" * 60)
    logger.info(f"  {BOT_NAME} v{BOT_VERSION}")
    logger.info(f"  Запуск: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Отключение предупреждений SSL
    import warnings
    warnings.filterwarnings("ignore")
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass
    
    # Проверка Python версии
    if sys.version_info < (3, 10):
        logger.error("Требуется Python 3.10 или выше!")
        sys.exit(1)
    
    logger.info(f"Python: {sys.version.split()[0]}")
    logger.info(f"ОС: {sys.platform}")
    logger.info(f"Хост: {socket.gethostname()}")
    
    # Создание и запуск бота
    bot = NavigatorBot(config)
    
    # Установка обработчиков сигналов
    _setup_signal_handlers(bot)
    
    # Запуск
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Принудительная остановка (Ctrl+C)")
        bot.request_shutdown()
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)
    
    logger.info("Программа завершена.")


# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================

if __name__ == "__main__":
    main()
