"""Корневой роутер API v1: собирает роутеры всех эндпоинтов."""

from fastapi import APIRouter

from backend.app.api.v1.endpoints import (
    admin_graph,
    admin_users,
    auth,
    branches,
    health,
    recommendations,
    reports,
    stats,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(stats.router)
api_router.include_router(reports.router)
api_router.include_router(recommendations.router)
api_router.include_router(branches.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_graph.router)
