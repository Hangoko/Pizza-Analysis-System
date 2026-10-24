"""
Наполнение БД демонстрационными данными.

Запуск из корня репозитория (после `alembic upgrade head`):
    python -m backend.app.scripts.seed

Создаёт 7 филиалов, 20 водителей и заказы из `data/synthetic_orders.csv`
(если файла нет — генерирует его через `generate_orders()`).
Если заданы `FIRST_ADMIN_USERNAME`/`FIRST_ADMIN_PASSWORD` и администраторов в БД нет —
создаёт первого администратора.
Скрипт идемпотентен: филиалы и водители ищутся по имени, заказы — по `external_id`,
повторный запуск не создаёт дублей.
"""

import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.core.config import BASE_DIR, get_settings
from backend.app.db.models import Branch, Driver, Order, OrderStatus
from backend.app.repositories.branch import BranchRepository
from backend.app.repositories.driver import DriverRepository
from backend.app.repositories.order import OrderRepository
from backend.app.services.auth_service import ensure_first_admin


# Филиалы, координаты и очереди — как в RoutingService.branches (ML-ядро).
# Ключ — номер филиала в синтетическом CSV (branch_id).
class BranchSeed(NamedTuple):
    name: str
    lat: float
    lon: float
    queue: int


BRANCHES: dict[int, BranchSeed] = {
    1: BranchSeed("Филиал Нижегородский", 56.322974, 44.034741, 5),
    2: BranchSeed("Филиал Автозавод", 56.241094, 43.861618, 1),
    3: BranchSeed("Филиал Сормово", 56.364246, 43.816756, 4),
    4: BranchSeed("Филиал Приокский", 56.245525, 43.985747, 2),
    5: BranchSeed("Филиал Московский", 56.326492, 43.871275, 3),
    6: BranchSeed("Филиал Канавинский", 56.312834, 43.937238, 6),
    7: BranchSeed("Филиал Советский", 56.293337, 44.013856, 0),
}
DRIVERS_COUNT = 20

# Время в CSV — локальное для Нижнего Новгорода (UTC+3, без перехода на летнее время)
LOCAL_TZ = timezone(timedelta(hours=3))


def driver_name(number: int) -> str:
    return f"Водитель {number:02d}"


def seed_branches(session: Session) -> dict[int, Branch]:
    """Создаёт недостающие филиалы. Возвращает соответствие «номер в CSV → Branch»."""
    repo = BranchRepository(session)
    result: dict[int, Branch] = {}
    for number, info in BRANCHES.items():
        branch = repo.get_by_name(info.name)
        if branch is None:
            branch = repo.add(
                Branch(name=info.name, lat=info.lat, lon=info.lon, current_queue=info.queue)
            )
        result[number] = branch
    return result


def seed_drivers(session: Session, branches: dict[int, Branch]) -> dict[int, Driver]:
    """Создаёт недостающих водителей, распределяя их по филиалам по кругу."""
    repo = DriverRepository(session)
    result: dict[int, Driver] = {}
    for number in range(1, DRIVERS_COUNT + 1):
        driver = repo.get_by_full_name(driver_name(number))
        if driver is None:
            branch = branches[(number - 1) % len(branches) + 1]
            driver = repo.add(
                Driver(
                    full_name=driver_name(number),
                    phone=f"+7900000{number:04d}",
                    branch_id=branch.id,
                )
            )
        result[number] = driver
    return result


def _optional_int(value: float | int | None) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def seed_orders(
    session: Session,
    csv_path: Path,
    branches: dict[int, Branch],
    drivers: dict[int, Driver],
) -> int:
    """Загружает заказы из CSV, пропуская уже существующие. Возвращает число новых."""
    repo = OrderRepository(session)
    existing = repo.existing_external_ids()
    df = pd.read_csv(csv_path)

    new_orders: list[Order] = []
    for row in df.itertuples(index=False):
        if row.order_id in existing:
            continue
        order_time = (
            datetime.strptime(str(row.order_time), "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=LOCAL_TZ)
            .astimezone(UTC)
        )
        delivery_minutes = _optional_int(row.delivery_time_minutes)
        delivered_at = None
        if row.status == OrderStatus.DELIVERED and delivery_minutes is not None:
            delivered_at = order_time + timedelta(minutes=delivery_minutes)
        driver_number = _optional_int(row.driver_id)

        new_orders.append(
            Order(
                external_id=str(row.order_id),
                client_lat=float(row.client_lat),
                client_lon=float(row.client_lon),
                branch_id=branches[int(row.branch_id)].id,
                driver_id=drivers[driver_number].id if driver_number in drivers else None,
                order_time=order_time,
                delivered_at=delivered_at,
                delivery_time_minutes=delivery_minutes,
                status=str(row.status),
            )
        )
        existing.add(str(row.order_id))

    if new_orders:
        repo.add_all(new_orders)
    return len(new_orders)


def ensure_orders_csv(data_dir: Path) -> Path:
    """Путь к CSV с заказами; если файла нет — генерирует его ML-генератором."""
    csv_path = data_dir / "synthetic_orders.csv"
    if not csv_path.exists():
        from backend.app.ml.data_generation.generator import generate_orders

        generate_orders()
        # Генератор пишет в <корень>/data; если DATA_DIR переопределён — берём оттуда
        generated = BASE_DIR / "data" / "synthetic_orders.csv"
        if not csv_path.exists() and generated.exists():
            return generated
    return csv_path


def seed(session: Session, csv_path: Path) -> dict[str, int]:
    """Полное наполнение БД в одной транзакции. Возвращает статистику."""
    branches = seed_branches(session)
    drivers = seed_drivers(session, branches)
    new_orders = seed_orders(session, csv_path, branches, drivers)
    session.commit()
    return {"branches": len(branches), "drivers": len(drivers), "new_orders": new_orders}


def main() -> None:
    from backend.app.db.session import SessionLocal

    settings = get_settings()
    csv_path = ensure_orders_csv(settings.DATA_DIR)
    with SessionLocal() as session:
        admin = ensure_first_admin(session, settings)
        stats = seed(session, csv_path)
    if admin is not None:
        print(f"Создан администратор: {admin.username}")
    print(
        f"Филиалов: {stats['branches']}, водителей: {stats['drivers']}, "
        f"новых заказов: {stats['new_orders']}"
    )


if __name__ == "__main__":
    main()
