"""
Конфигурация приложения.

Все параметры читаются из переменных окружения и (опционально) из файла `.env`
в корне репозитория. Значения по умолчанию подходят для локальной разработки.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Корень репозитория: backend/app/core/config.py -> 3 уровня вверх
BASE_DIR = Path(__file__).resolve().parents[3]

# Небезопасный секрет для разработки: при его использовании приложение пишет предупреждение
DEV_JWT_SECRET_KEY = "dev-only-insecure-jwt-secret-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Общие параметры приложения ---
    APP_NAME: str = "NewFastPizza Analytics API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # --- База данных ---
    DATABASE_URL: str = "postgresql+psycopg://pizza:pizza@localhost:5432/pizza"

    # --- JWT ---
    # Значение по умолчанию — ТОЛЬКО для локальной разработки; в production задать в env
    JWT_SECRET_KEY: str = DEV_JWT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- CORS: список origin через запятую или JSON-массив ---
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost",
        "http://localhost:5173",
    ]

    # --- Данные и граф дорог ---
    DATA_DIR: Path = BASE_DIR / "data"
    # Если не задан — берётся <DATA_DIR>/nn_graph.pkl
    GRAPH_PATH: Path | None = None
    # Загружать граф в фоне при старте; при false эндпоинты маршрутов отвечают 503,
    # а /health/ready не считает отсутствие графа неготовностью
    LOAD_GRAPH_ON_STARTUP: bool = True
    # Если файла графа нет — скачать его из OpenStreetMap (несколько минут) и сохранить
    GRAPH_DOWNLOAD_IF_MISSING: bool = True
    # Точка водителя дальше этого расстояния от ближайшего узла графа — ошибка 422
    ROUTE_MAX_SNAP_DISTANCE_KM: float = 2.0

    # --- Первый администратор (создаётся, если админов ещё нет) ---
    FIRST_ADMIN_USERNAME: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None
    FIRST_ADMIN_EMAIL: str | None = None

    # --- Регистрация ---
    ALLOW_PUBLIC_REGISTRATION: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Разрешаем задавать origin'ы строкой через запятую или JSON-массивом."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _default_graph_path(self) -> "Settings":
        """Путь к графу по умолчанию лежит в каталоге данных."""
        if self.GRAPH_PATH is None:
            self.GRAPH_PATH = self.DATA_DIR / "nn_graph.pkl"
        return self


@lru_cache
def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэшируется)."""
    return Settings()
