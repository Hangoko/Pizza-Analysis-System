"""
Точка входа FastAPI-приложения NewFastPizza.

Запуск из корня репозитория:
    uvicorn backend.app.main:app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import api_router
from backend.app.core.config import DEV_JWT_SECRET_KEY, Settings, get_settings

logger = logging.getLogger(__name__)

# Описание групп эндпоинтов для Swagger / ReDoc
OPENAPI_TAGS = [
    {"name": "health", "description": "Проверка состояния сервиса"},
    {"name": "auth", "description": "Регистрация, вход, текущий пользователь (JWT)"},
    {"name": "stats", "description": "KPI и агрегированная статистика заказов"},
    {"name": "reports", "description": "Шаблоны отчётов, конструктор и экспорт CSV"},
    {"name": "recommendations", "description": "Рекомендации водителям и по филиалам"},
    {"name": "branches", "description": "Филиалы и их очереди заказов"},
    {"name": "admin", "description": "Администрирование пользователей и графа дорог"},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Инициализация и освобождение ресурсов приложения."""
    # Заготовка: загрузка графа дорог в фоне (этап 6).
    # Первый администратор создаётся скриптом seed (FIRST_ADMIN_*), а не при старте.
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Фабрика приложения: настройки, middleware, роутеры."""
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend системы анализа заказов, KPI и рекомендаций NewFastPizza.",
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if settings.JWT_SECRET_KEY == DEV_JWT_SECRET_KEY:
        logger.warning("JWT_SECRET_KEY не задан — используется небезопасный dev-ключ")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
