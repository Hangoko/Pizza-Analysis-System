"""Схемы /admin/graph."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GraphBBox(BaseModel):
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


class GraphInfo(BaseModel):
    status: str = Field(description="not_loaded / loading / ready / failed")
    error: str | None = None
    version: int | None = None
    source: str | None = Field(default=None, description="Откуда загружен текущий граф")
    nodes: int | None = None
    edges: int | None = None
    loaded_at: datetime | None = None
    bbox: GraphBBox | None = None
    branch_nodes_cached: int | None = None
    graph_path: str
    file_exists: bool
    file_size_bytes: int | None = None
    file_modified_at: datetime | None = None
    upload_max_mb: float


class WeightSkip(BaseModel):
    row: int = Field(description="Номер строки данных (с 1)")
    reason: str


class WeightsUpdateReport(BaseModel):
    filename: str | None
    format: Literal["csv", "json"]
    rows_total: int
    rows_applied: int
    rows_skipped: int
    edges_updated: int
    skipped: list[WeightSkip] = Field(description="Причины пропуска (не более 50)")
    skipped_truncated: bool
    changed: bool = Field(description="Граф заменён (была хотя бы одна корректная строка)")
    persisted: bool = Field(description="Новый граф сохранён в GRAPH_PATH")
    graph: GraphInfo
    elapsed_ms: float


class GraphChangeResult(BaseModel):
    action: Literal["upload", "reload"]
    format: Literal["graphml", "node-link", "pickle"]
    persisted: bool
    graph: GraphInfo
    elapsed_ms: float
