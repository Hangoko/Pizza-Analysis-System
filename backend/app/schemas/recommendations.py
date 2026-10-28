"""Схемы /recommendations и /branches."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DriverRecommendation(BaseModel):
    branch_id: int
    branch_name: str
    travel_time_minutes: float = Field(description="Время в пути по графу дорог, мин")
    queue_size: int = Field(description="Текущая очередь заказов филиала")
    score: float = Field(description="Оценка: минуты в пути - очередь * 2 (меньше — лучше)")
    driver_node: int | str
    branch_node: int | str
    route: list[list[float]] = Field(description="Маршрут: список точек `[lat, lon]`")
    graph_version: int
    elapsed_ms: float = Field(description="Время расчёта на сервере, мс")


class DemandZone(BaseModel):
    zone_id: int
    center_lat: float
    center_lon: float
    order_count: int
    recommendation: str = Field(
        description="Открыть филиал / Закрыть филиал / Филиал рентабелен / Спрос низкий"
    )
    nearest_branch_id: int | None
    nearest_branch_name: str | None
    distance_to_branch_km: float | None


class DemandZonesResponse(BaseModel):
    n_clusters: int
    date_from: datetime | None
    date_to: datetime | None
    orders_count: int = Field(description="Доставленных заказов за период")
    zones: list[DemandZone]
    elapsed_ms: float


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lat: float
    lon: float
    current_queue: int
    is_active: bool


class BranchQueueUpdate(BaseModel):
    current_queue: int = Field(ge=0, le=10_000, description="Новая очередь заказов")
