"""
Администрирование графа дорог: сводка, обновление весов (пробки), загрузка нового графа,
перечитывание с диска.

Все изменения выполняются под `GraphRegistry.mutation_lock` по одной схеме:
правка **копии** графа → проверка → атомарное сохранение в `GRAPH_PATH`
(временный файл + `os.replace`) → `GraphRegistry.replace_graph` (новый индекс узлов и кэш
узлов филиалов). Запросы маршрутов, начатые до замены, досчитываются на старом снимке.

От пользователя принимаются только GraphML и JSON node-link. Pickle не принимается
никогда: его распаковка выполняет произвольный код. Pickle пишет и читает только сервер.
"""

import csv
import io
import json
import math
import os
import pickle
import tempfile
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal

import networkx as nx
import osmnx as ox

from backend.app.core.config import Settings
from backend.app.core.graph_state import GraphRegistry, GraphStatus, read_graph_file

MAX_REASONS = 50
WEIGHT_ATTR = "travel_time"
# Исходное (без пробок) время проезда: множитель всегда применяется к нему, а не накапливается
BASE_WEIGHT_ATTR = "travel_time_base"
PICKLE_SUFFIXES = frozenset({".pkl", ".pickle", ".p", ".pck", ".joblib", ".dill"})
_CHUNK = 1024 * 1024
_UTF8_BOM = b"\xef\xbb\xbf"


class GraphAdminError(Exception):
    """Ошибка операции с графом; `status_code` — HTTP-код для слоя API."""

    status_code = 400

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class GraphFormatError(GraphAdminError):
    status_code = 422


class UnsupportedFormatError(GraphAdminError):
    status_code = 415


class UploadTooLargeError(GraphAdminError):
    status_code = 413


class GraphBusyError(GraphAdminError):
    status_code = 409


class GraphNotReadyError(GraphAdminError):
    status_code = 503


class GraphFileMissingError(GraphAdminError):
    status_code = 404


class GraphPersistError(GraphAdminError):
    status_code = 500


# --- файлы ---


def save_upload(source: IO[bytes], target: Path, max_bytes: int) -> int:
    """Копирует загрузку на диск по частям; больше `max_bytes` — `UploadTooLargeError`."""
    size = 0
    with target.open("wb") as out:
        while chunk := source.read(_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise UploadTooLargeError(f"Файл больше допустимых {max_bytes / 1024 / 1024:g} МБ")
            out.write(chunk)
    if size == 0:
        raise GraphFormatError("Пустой файл")
    return size


def _head(path: Path, size: int = 64) -> bytes:
    with path.open("rb") as file:
        head = file.read(size)
    return head.removeprefix(_UTF8_BOM).lstrip()


def _reject_pickle(path: Path, filename: str | None) -> None:
    suffix = Path(filename or "").suffix.lower()
    # Протокол pickle 2+ начинается с опкода PROTO (0x80)
    if suffix in PICKLE_SUFFIXES or _head(path)[:1] == b"\x80":
        raise UnsupportedFormatError(
            "Pickle не принимается (распаковка выполняет произвольный код): "
            "используйте GraphML или JSON node-link"
        )


def persist_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    """Атомарная запись pickle: временный файл в том же каталоге → fsync → `os.replace`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as file:
            pickle.dump(graph, file, protocol=pickle.HIGHEST_PROTOCOL)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# --- разбор и проверка графа ---


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def validate_graph(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Узлы должны иметь числовые `x` (долгота) и `y` (широта), рёбра — `travel_time` > 0 (с).
    Значения приводятся к float. Ошибки собираются (не более `MAX_REASONS`) → 422.
    """
    errors: list[str] = []

    def error(message: str) -> None:
        if len(errors) < MAX_REASONS:
            errors.append(message)

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise GraphFormatError("Граф должен содержать узлы и рёбра")
    for node, data in graph.nodes(data=True):
        x, y = _to_float(data.get("x")), _to_float(data.get("y"))
        if x is None or y is None:
            error(f"Узел {node!r}: нет числовых координат x/y")
        elif not (-180 <= x <= 180 and -90 <= y <= 90):
            error(f"Узел {node!r}: координаты вне диапазона (x — долгота, y — широта)")
        else:
            data["x"], data["y"] = x, y
    for u, v, key, data in graph.edges(keys=True, data=True):
        weight = _to_float(data.get(WEIGHT_ATTR))
        if weight is None or weight <= 0:
            error(f"Ребро ({u!r}, {v!r}, {key!r}): нужен travel_time > 0 (секунды)")
        else:
            data[WEIGHT_ATTR] = weight
    if errors:
        raise GraphFormatError("Граф не прошёл проверку", errors)
    return graph


def _load_graphml(path: Path) -> nx.MultiDiGraph:
    """
    GraphML от osmnx (`ox.save_graphml`, все атрибуты строками) читается `ox.load_graphml` —
    он приводит типы и id узлов к int. Если не вышло (GraphML от networkx с типизированными
    атрибутами, нецелые id), читаем `nx.read_graphml`; типы x/y/travel_time приведёт проверка.
    """
    try:
        return ox.load_graphml(path)
    except Exception:  # noqa: BLE001, S110 — пробуем networkx
        pass
    try:
        graph = nx.MultiDiGraph(nx.read_graphml(path, force_multigraph=True))
    except Exception as exc:  # noqa: BLE001 — любая ошибка разбора → 422
        raise GraphFormatError(f"Некорректный GraphML: {exc}") from exc
    if all(isinstance(node, str) and node.lstrip("-").isdigit() for node in graph):
        graph = nx.relabel_nodes(graph, int)
    return graph


def _load_node_link(path: Path) -> nx.MultiDiGraph:
    try:
        with path.open(encoding="utf-8-sig") as file:
            data = json.load(file)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraphFormatError(f"Некорректный JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        raise GraphFormatError("JSON node-link: нужен объект с массивом nodes")
    edges_key = "links" if "links" in data and "edges" not in data else "edges"
    if not isinstance(data.get(edges_key, []), list):
        raise GraphFormatError(f"JSON node-link: {edges_key} должен быть массивом")
    data.setdefault(edges_key, [])
    try:
        graph = nx.node_link_graph(data, directed=True, multigraph=True, edges=edges_key)
    except Exception as exc:  # noqa: BLE001 — KeyError/TypeError/NetworkXError → 422
        raise GraphFormatError(f"Некорректный JSON node-link: {exc!r}") from exc
    return graph if isinstance(graph, nx.MultiDiGraph) else nx.MultiDiGraph(graph)


def parse_graph_file(
    path: Path, filename: str | None
) -> tuple[nx.MultiDiGraph, Literal["graphml", "node-link"]]:
    _reject_pickle(path, filename)
    suffix = Path(filename or "").suffix.lower()
    head = _head(path)
    if suffix in {".graphml", ".xml"} or (suffix != ".json" and head.startswith(b"<")):
        graph, fmt = _load_graphml(path), "graphml"
    elif suffix == ".json" or head.startswith(b"{"):
        graph, fmt = _load_node_link(path), "node-link"
    else:
        raise UnsupportedFormatError("Поддерживаются GraphML (.graphml) и JSON node-link (.json)")
    return validate_graph(graph), fmt


# --- веса рёбер ---


@dataclass(frozen=True, slots=True)
class WeightRow:
    row: int
    u: Any
    v: Any
    key: Any | None
    travel_time: float | None
    multiplier: float | None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _read_weight_records(path: Path, filename: str | None) -> tuple[list[Any], str]:
    _reject_pickle(path, filename)
    suffix = Path(filename or "").suffix.lower()
    is_json = suffix == ".json" or _head(path)[:1] in (b"[", b"{")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GraphFormatError("Файл должен быть в кодировке UTF-8") from exc
    if is_json:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GraphFormatError(f"Некорректный JSON: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("rows", data.get("edges"))
        if not isinstance(data, list):
            raise GraphFormatError("JSON: нужен массив строк или объект с массивом rows")
        return data, "json"

    reader = csv.DictReader(io.StringIO(text), delimiter=_csv_delimiter(text))
    columns = {name.strip().lower() for name in reader.fieldnames or [] if name}
    if not {"u", "v"} <= columns or not columns & {"travel_time", "multiplier"}:
        raise GraphFormatError("CSV: нужны колонки u, v и travel_time или multiplier (key — опц.)")
    records = [
        {
            (k or "").strip().lower(): (val.strip() if isinstance(val, str) else val)
            for k, val in record.items()
        }
        for record in reader
    ]
    return records, "csv"


def _csv_delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    return ";" if header.count(";") > header.count(",") else ","


def _resolve_node(graph: nx.MultiDiGraph, raw: Any) -> Any | None:
    """Id узла из файла: как есть, иначе как целое (в CSV всё — строки)."""
    if isinstance(raw, bool) or _blank(raw):
        return None
    if not isinstance(raw, list | dict) and raw in graph:
        return raw
    try:
        as_int = int(str(raw).strip())
    except ValueError:
        return None
    return as_int if as_int in graph else None


def _parse_weight_row(graph: nx.MultiDiGraph, number: int, record: Any) -> WeightRow | str:
    """Строка весов или текст причины пропуска."""
    if not isinstance(record, dict):
        return "строка должна быть объектом"
    u, v = _resolve_node(graph, record.get("u")), _resolve_node(graph, record.get("v"))
    if u is None or v is None:
        missing = "u" if u is None else "v"
        return f"узел {missing}={record.get(missing)!r} отсутствует в графе"

    key = record.get("key")
    if _blank(key):
        key = None
        if not graph.has_edge(u, v):
            return f"ребра {u}→{v} нет в графе"
    else:
        if isinstance(key, str):
            try:
                key = int(key)
            except ValueError:
                return f"некорректный key={key!r}"
        if not graph.has_edge(u, v, key):
            return f"ребра {u}→{v} с key={key!r} нет в графе"

    raw_time, raw_mult = record.get("travel_time"), record.get("multiplier")
    if _blank(raw_time) == _blank(raw_mult):
        return "нужно ровно одно из полей: travel_time или multiplier"
    field, raw = ("travel_time", raw_time) if not _blank(raw_time) else ("multiplier", raw_mult)
    value = None if isinstance(raw, bool) else _to_float(raw)
    if value is None or value <= 0:
        return f"{field} должен быть числом > 0, получено {raw!r}"
    if field == "travel_time":
        return WeightRow(number, u, v, key, value, None)
    return WeightRow(number, u, v, key, None, value)


def apply_weights(
    graph: nx.MultiDiGraph, rows: Iterable[WeightRow]
) -> tuple[int, list[tuple[int, str]]]:
    """Применяет строки к графу (копии!). Возвращает (число рёбер, пропуски)."""
    edges_updated = 0
    skipped: list[tuple[int, str]] = []
    for row in rows:
        keys = [row.key] if row.key is not None else list(graph[row.u][row.v])
        attrs_list = [graph[row.u][row.v][key] for key in keys]
        if row.multiplier is not None and any(
            _to_float(a.get(BASE_WEIGHT_ATTR, a.get(WEIGHT_ATTR))) is None for a in attrs_list
        ):
            skipped.append((row.row, "у ребра нет travel_time — множитель не к чему применить"))
            continue
        for attrs in attrs_list:
            if BASE_WEIGHT_ATTR not in attrs and _to_float(attrs.get(WEIGHT_ATTR)) is not None:
                attrs[BASE_WEIGHT_ATTR] = float(attrs[WEIGHT_ATTR])
            if row.multiplier is not None:
                attrs[WEIGHT_ATTR] = attrs[BASE_WEIGHT_ATTR] * row.multiplier
            else:
                attrs[WEIGHT_ATTR] = row.travel_time
            edges_updated += 1
    return edges_updated, skipped


# --- сервис ---


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


class GraphService:
    def __init__(self, registry: GraphRegistry, settings: Settings) -> None:
        self.registry = registry
        self.settings = settings
        self.path: Path = settings.GRAPH_PATH
        self.max_bytes = int(settings.GRAPH_UPLOAD_MAX_MB * 1024 * 1024)

    def info(self) -> dict[str, Any]:
        info = self.registry.info()
        snapshot = self.registry.snapshot()
        info["bbox"] = vars(snapshot.bbox) if snapshot else None
        info["branch_nodes_cached"] = len(snapshot.cached_branch_coords) if snapshot else None
        info["graph_path"] = str(self.path)
        info["upload_max_mb"] = self.settings.GRAPH_UPLOAD_MAX_MB
        try:
            stat = self.path.stat()
        except OSError:
            info.update(file_exists=False, file_size_bytes=None, file_modified_at=None)
        else:
            info.update(
                file_exists=True,
                file_size_bytes=stat.st_size,
                file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        return info

    # --- операции ---

    def update_weights(self, upload: IO[bytes], filename: str | None) -> dict[str, Any]:
        started = time.perf_counter()
        with self._mutation(), tempfile.TemporaryDirectory(prefix="pizza-weights-") as tmp:
            snapshot = self.registry.snapshot()
            if snapshot is None:
                raise GraphNotReadyError("Граф дорог не загружен — веса обновлять не к чему")
            path = Path(tmp) / "weights"
            save_upload(upload, path, self.max_bytes)
            records, fmt = _read_weight_records(path, filename)

            rows: list[WeightRow] = []
            skipped: list[tuple[int, str]] = []
            for number, record in enumerate(records, start=1):
                parsed = _parse_weight_row(snapshot.graph, number, record)
                if isinstance(parsed, str):
                    skipped.append((number, parsed))
                else:
                    rows.append(parsed)

            edges_updated, apply_skipped = 0, []
            changed = persisted = False
            if rows:
                graph = snapshot.graph.copy()
                edges_updated, apply_skipped = apply_weights(graph, rows)
                if edges_updated:
                    self._persist_and_replace(graph, source=f"weights:{filename or 'upload'}")
                    changed = persisted = True
            skipped += apply_skipped
            skipped.sort()

        return {
            "filename": filename,
            "format": fmt,
            "rows_total": len(records),
            "rows_applied": len(rows) - len(apply_skipped),
            "rows_skipped": len(skipped),
            "edges_updated": edges_updated,
            "skipped": [{"row": n, "reason": r} for n, r in skipped[:MAX_REASONS]],
            "skipped_truncated": len(skipped) > MAX_REASONS,
            "changed": changed,
            "persisted": persisted,
            "graph": self.info(),
            "elapsed_ms": _elapsed_ms(started),
        }

    def upload(self, upload: IO[bytes], filename: str | None) -> dict[str, Any]:
        started = time.perf_counter()
        with self._mutation(), tempfile.TemporaryDirectory(prefix="pizza-graph-") as tmp:
            path = Path(tmp) / "graph"
            save_upload(upload, path, self.max_bytes)
            graph, fmt = parse_graph_file(path, filename)
            self._persist_and_replace(graph, source=f"upload:{filename or 'graph'}")
        return {
            "action": "upload",
            "format": fmt,
            "persisted": True,
            "graph": self.info(),
            "elapsed_ms": _elapsed_ms(started),
        }

    def reload(self) -> dict[str, Any]:
        started = time.perf_counter()
        with self._mutation():
            if not self.path.exists():
                raise GraphFileMissingError(f"Файл графа не найден: {self.path}")
            try:
                # Файл в GRAPH_PATH пишет только сервер — pickle здесь допустим
                graph = read_graph_file(self.path, allow_download=False)
                self.registry.replace_graph(graph, source=str(self.path))
            except Exception as exc:  # noqa: BLE001 — повреждённый файл → 422, граф прежний
                raise GraphFormatError(f"Не удалось загрузить граф из файла: {exc}") from exc
        return {
            "action": "reload",
            "format": "pickle",
            "persisted": False,
            "graph": self.info(),
            "elapsed_ms": _elapsed_ms(started),
        }

    # --- внутреннее ---

    @contextmanager
    def _mutation(self) -> Iterator[None]:
        """Блокировка изменений; пока граф грузится при старте — 409."""
        with self.registry.mutation_lock:
            if self.registry.status == GraphStatus.LOADING:
                raise GraphBusyError("Граф загружается при старте — повторите позже")
            yield

    def _persist_and_replace(self, graph: nx.MultiDiGraph, *, source: str) -> None:
        # Сначала диск: если запись не удалась, в памяти остаётся прежний согласованный граф
        try:
            persist_graph(graph, self.path)
        except OSError as exc:
            raise GraphPersistError(f"Не удалось сохранить граф в {self.path}: {exc}") from exc
        self.registry.replace_graph(graph, source=source)


__all__ = [
    "GraphAdminError",
    "GraphService",
    "apply_weights",
    "parse_graph_file",
    "persist_graph",
    "validate_graph",
]
