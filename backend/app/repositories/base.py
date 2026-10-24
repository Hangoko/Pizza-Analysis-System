"""Generic-репозиторий: базовые CRUD-операции над одной моделью."""

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Base


class BaseRepository[ModelT: Base]:
    """Базовый репозиторий. Наследник задаёт атрибут `model`."""

    model: ClassVar[type[Any]]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, obj_id: int) -> ModelT | None:
        return self.session.get(self.model, obj_id)

    def list(self, *, offset: int = 0, limit: int | None = None) -> Sequence[ModelT]:
        stmt = select(self.model).order_by(self.model.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.session.scalars(stmt).all()

    def add(self, obj: ModelT) -> ModelT:
        """Добавляет объект в сессию и выполняет flush (появляется `id`)."""
        self.session.add(obj)
        self.session.flush()
        return obj

    def add_all(self, objs: Sequence[ModelT]) -> None:
        self.session.add_all(objs)
        self.session.flush()

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()
