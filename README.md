# Pizza-Analysis-System
Сбор метрик заказов, генерация отчетов, рекомендации по маршрутам, оптимизация сети филиалов.


## Запуск бэкенда локально

Подробная документация API (все эндпоинты, параметры, примеры JSON, ошибки) — [backend/README.md](backend/README.md).

Требуется **Python 3.12** (на более новых версиях у pandas / scikit-learn / osmnx может не быть колёс).
Все команды выполняются из корня репозитория.

```powershell
# 1. Виртуальное окружение
py -3.12 -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate

# 2. Зависимости (рабочие + тесты и линтер)
python -m pip install -r backend/requirements-dev.txt

# 3. Запуск API с автоперезагрузкой
uvicorn backend.app.main:app --reload
```

После запуска:

- Swagger UI — http://localhost:8000/docs
- ReDoc — http://localhost:8000/redoc
- OpenAPI-схема — http://localhost:8000/openapi.json
- Проверка состояния — http://localhost:8000/api/v1/health и `/api/v1/health/ready`

Настройки читаются из переменных окружения или файла `.env` в корне
(см. `backend/app/core/config.py`).

### База данных: миграции и демо-данные

Нужен PostgreSQL; строка подключения — `DATABASE_URL`
(по умолчанию `postgresql+psycopg://pizza:pizza@localhost:5432/pizza`).
Для локальной разработки БД можно поднять в Docker:

```powershell
docker run -d --name pizza-pg -e POSTGRES_USER=pizza -e POSTGRES_PASSWORD=pizza `
  -e POSTGRES_DB=pizza -p 5432:5432 postgres:16-alpine

# Применить миграции (из корня репозитория)
alembic -c backend/alembic.ini upgrade head

# Наполнить БД: 7 филиалов, 20 водителей, заказы из data/synthetic_orders.csv
# (если CSV нет — он будет сгенерирован). Повторный запуск дублей не создаёт.
python -m backend.app.scripts.seed
```

Новая миграция после изменения моделей:
`alembic -c backend/alembic.ini revision --autogenerate -m "описание"`.
ER-диаграмма схемы — [docs/er-diagram.md](docs/er-diagram.md).

### Аутентификация и роли

JWT (HS256), эндпоинты `/api/v1/auth`:

- `POST /register` — саморегистрация (JSON `username`, `password` 8+ символов и не длиннее 72 байт,
  опционально `email`, `full_name`). Роль всегда `driver`; повышает её администратор.
  Отключается `ALLOW_PUBLIC_REGISTRATION=false` (тогда 403).
- `POST /login` — OAuth2 password flow (form-data `username`/`password`), возвращает `access_token`.
  В Swagger работает кнопка **Authorize**.
- `GET /me` — текущий пользователь (заголовок `Authorization: Bearer <token>`).

Переменные окружения: `JWT_SECRET_KEY` (**в production обязательно задать**; значение по умолчанию
только для разработки, при нём в лог пишется предупреждение), `JWT_ALGORITHM`,
`ACCESS_TOKEN_EXPIRE_MINUTES`.
Первый администратор создаётся командой `python -m backend.app.scripts.seed`, если заданы
`FIRST_ADMIN_USERNAME`, `FIRST_ADMIN_PASSWORD` (и опционально `FIRST_ADMIN_EMAIL`) и
администраторов в БД ещё нет; повторный запуск ничего не меняет.

Пользователь читается из БД на каждый запрос: блокировка (`is_active=false` → 403) и смена роли
действуют сразу. Без токена или с неверным/просроченным токеном — 401, с неподходящей ролью — 403.

Матрица доступа:

| Функция | admin | manager | executive | driver |
|---|---|---|---|---|
| KPI / статистика | ✓ | ✓ | ✓ | — |
| Шаблоны и экспорт CSV | ✓ | ✓ (свои + системные) | ✓ (чтение/экспорт) | — |
| Рекомендации по филиалам (K-Means) | ✓ | ✓ | ✓ | — |
| Рекомендация водителю | ✓ | ✓ | — | ✓ |
| Управление пользователями, граф | ✓ | — | — | — |

В коде роли проверяются зависимостью `require_roles(...)` из `backend/app/api/deps.py`.

### Рекомендации и граф дорог

Граф дорог Нижнего Новгорода (`GRAPH_PATH`, по умолчанию `data/nn_graph.pkl`) загружается
при старте **в фоновом потоке** (`LOAD_GRAPH_ON_STARTUP=true`), API отвечает сразу. Если файла
нет и `GRAPH_DOWNLOAD_IF_MISSING=true`, граф скачивается из OpenStreetMap (1–3 минуты) и
сохраняется. Пока граф не готов, эндпоинты маршрутов отвечают **503** с `Retry-After`.
`/api/v1/health/ready` показывает компонент `graph`: при `LOAD_GRAPH_ON_STARTUP=true` загрузка
(`loading`) и ошибка (`error`) дают 503; при `false` граф необязателен (`not_configured`).

Эндпоинты `/api/v1/recommendations`:

- `GET /driver?lat=&lon=` (admin, manager, driver) — лучший филиал: минимум
  `минуты в пути - очередь * 2`; в ответе филиал, время, очередь, маршрут `[[lat, lon], ...]`,
  `elapsed_ms`. Точка дальше `ROUTE_MAX_SNAP_DISTANCE_KM` (2 км) от дорог графа — 422,
  нет маршрута — 404.
- `GET /driver/map?lat=&lon=` — то же в виде HTML-карты (folium).
- `GET /branches?n_clusters=7&date_from=&date_to=` (admin, manager, executive) — зоны спроса
  K-Means по доставленным заказам и вердикт по филиалам; если заказов меньше `n_clusters` — 422.
- `GET /branches/map` — HTML-карта: тепловая карта заказов, филиалы, центроиды.

Филиалы: `GET /api/v1/branches` (все роли), `PATCH /api/v1/branches/{id}/queue`
(admin, manager, тело `{"current_queue": 3}`) — очередь сразу учитывается в рекомендации.

Расчёт маршрута использует ML-код без изменений (`RoutingService`, `KMeansAnalyzer`, генераторы
карт); ускорение — подкласс `FastRoutingService` (`backend/app/services/routing_adapter.py`):
индекс ближайших узлов строится один раз, узлы филиалов кэшируются, Дейкстра запускается один
раз от водителя.

### Администрирование (только admin)

Пользователи — `/api/v1/admin/users`:

- `GET ?role=&is_active=&search=&limit=50&offset=0` — список с `total`; `search` — подстрока
  логина или ФИО.
- `POST` — сотрудник с любой ролью (`username`, `password`, `role`, опц. `email`, `full_name`,
  `is_active`, `driver_id` — привязка к записи водителя, только для роли `driver`).
- `GET /{id}`, `PATCH /{id}` — роль, ФИО, email, `is_active`, сброс пароля (`password`),
  `driver_id` (`null` — отвязать; смена роли с `driver` отвязывает автоматически).
- `DELETE /{id}` — мягкая деактивация (`is_active=false`), вернуть — `PATCH {"is_active": true}`.

Нельзя деактивировать или понизить себя и последнего активного администратора — **409**.

Граф дорог — `/api/v1/admin/graph`:

- `GET /info` — статус, версия, источник, узлы/рёбра, `loaded_at`, файл `GRAPH_PATH`.
- `POST /weights` (multipart `file`, CSV или JSON) — веса пробок. Строка: `u`, `v`, опц. `key`
  (без него — все параллельные рёбра u→v) и ровно одно из `travel_time` (секунды) или
  `multiplier` (к исходному времени без пробок, не накапливается; `1` — снять пробку).
  Некорректные строки пропускаются, в ответе `rows_applied`/`rows_skipped` и причины (до 50).
- `POST /upload` (multipart `file`) — новый граф: GraphML (`ox.save_graphml` / `nx.write_graphml`)
  или JSON node-link (`nx.node_link_data`). У узлов обязательны `x` (долгота) и `y` (широта),
  у рёбер — `travel_time` > 0, иначе **422** со списком ошибок. **Pickle не принимается**
  (выполнение кода при распаковке) — **415**.
- `POST /reload` — перечитать граф из `GRAPH_PATH`.

Изменения применяются к копии графа, сохраняются в `GRAPH_PATH` атомарно (временный файл +
`os.replace`) и подменяют граф в памяти без остановки; параллельные изменения выполняются по
очереди. Лимит файла — `GRAPH_UPLOAD_MAX_MB` (100), больше — **413**; пока граф грузится при
старте — **409**.

```csv
u,v,key,multiplier,travel_time
1226461234,1226461301,,3,
1226461301,1226461288,0,,45.5
```

```powershell
curl.exe -H "Authorization: Bearer $token" -F "file=@jam.csv" http://localhost:8000/api/v1/admin/graph/weights
```

Проверки перед коммитом:

```powershell
ruff check backend
ruff format --check backend
pytest -q
```
