"""Корневой роутер API v1: собирает роутеры всех эндпоинтов."""

from fastapi import APIRouter

from backend.app.api.v1.endpoints import health

api_router = APIRouter()
api_router.include_router(health.router)
