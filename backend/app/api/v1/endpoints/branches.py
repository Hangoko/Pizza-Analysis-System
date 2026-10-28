"""Филиалы: список и обновление текущей очереди заказов."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.deps import DbSession, require_roles
from backend.app.db.models.user import UserRole
from backend.app.repositories.branch import BranchRepository
from backend.app.schemas.recommendations import BranchQueueUpdate, BranchRead

# Список нужен всем ролям (водителю — чтобы видеть филиалы и очереди)
READ_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EXECUTIVE, UserRole.DRIVER)
QUEUE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)

router = APIRouter(
    prefix="/branches",
    tags=["branches"],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав"},
    },
)


@router.get(
    "",
    response_model=list[BranchRead],
    summary="Список филиалов",
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def list_branches(
    db: DbSession,
    include_inactive: Annotated[bool, Query(description="Включить закрытые филиалы")] = False,
) -> list[BranchRead]:
    repo = BranchRepository(db)
    branches = repo.list() if include_inactive else repo.list_active()
    return [BranchRead.model_validate(branch) for branch in branches]


@router.patch(
    "/{branch_id}/queue",
    response_model=BranchRead,
    summary="Обновить очередь заказов филиала",
    dependencies=[Depends(require_roles(*QUEUE_ROLES))],
    responses={404: {"description": "Филиал не найден"}},
)
def update_branch_queue(branch_id: int, body: BranchQueueUpdate, db: DbSession) -> BranchRead:
    """Очередь сразу учитывается в `/recommendations/driver`. Роли: admin, manager."""
    branch = BranchRepository(db).get(branch_id)
    if branch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Филиал не найден")
    branch.current_queue = body.current_queue
    db.commit()
    return BranchRead.model_validate(branch)
