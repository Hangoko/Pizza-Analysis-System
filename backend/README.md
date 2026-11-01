# Backend NewFastPizza — REST API

FastAPI-бэкенд системы анализа заказов NewFastPizza: KPI и статистика, конструктор отчётов
с экспортом в CSV, рекомендации водителям по графу дорог, зоны спроса (K-Means),
администрирование пользователей и графа дорог.

Документ описывает **фактическое поведение кода**. Все примеры ответов ниже сняты с живого
сервера (PostgreSQL 16 + демо-данные из `seed` + граф `data/nn_graph.pkl`); длинные массивы
сокращены до нескольких элементов и помечены `…`. Интерактивная документация — Swagger
`/docs` и ReDoc `/redoc` (OpenAPI-схема — `/openapi.json`).

## Содержание

1. [Архитектура](#1-архитектура)
2. [Быстрый старт](#2-быстрый-старт)
3. [Настройки (переменные окружения)](#3-настройки-переменные-окружения)
4. [Авторизация и роли](#4-авторизация-и-роли)
5. [Общие соглашения](#5-общие-соглашения)
6. [Сводная таблица эндпоинтов](#6-сводная-таблица-эндпоинтов)
7. [health — состояние сервиса](#7-health--состояние-сервиса)
8. [auth — регистрация и вход](#8-auth--регистрация-и-вход)
9. [stats — KPI и статистика](#9-stats--kpi-и-статистика)
10. [reports — шаблоны, конструктор, CSV](#10-reports--шаблоны-конструктор-csv)
11. [recommendations — рекомендации](#11-recommendations--рекомендации)
12. [branches — филиалы и очереди](#12-branches--филиалы-и-очереди)
13. [admin/users — пользователи](#13-adminusers--пользователи)
14. [admin/graph — граф дорог](#14-admingraph--граф-дорог)
15. [Граф дорог: жизненный цикл](#15-граф-дорог-жизненный-цикл)
16. [Тесты и линтер](#16-тесты-и-линтер)

---

## 1. Архитектура

Модульный монолит, слоистая архитектура (Layered) + паттерн Repository:

```
HTTP ─► api (роутеры, зависимости, HTTP-коды)
          └─► services (бизнес-логика, без знания про HTTP)
                ├─► repositories (запросы SQLAlchemy) ─► db (модели, сессия) ─► PostgreSQL
                └─► ml (RoutingService, KMeansAnalyzer, генераторы карт — код ML-команды)
```

- **api** переводит доменные исключения сервисов в HTTP-коды, проверяет роли
  (`require_roles`), валидирует вход через Pydantic-схемы.
- **services** — чистая логика: KPI считаются на pandas/NumPy (`stats_service`), отчёты
  переиспользуют ту же агрегацию (`report_service`), маршруты — адаптер над ML-кодом
  (`routing_adapter`), K-Means — `demand_adapter`.
- **ml** — код ML-части (`backend/app/ml/`), используется без изменений через тонкие
  подклассы-адаптеры.
- **core** — настройки, JWT/пароли, состояние графа дорог в памяти (`graph_state`).

```
backend/
├── alembic/                 миграции БД (alembic.ini рядом)
├── app/
│   ├── main.py              create_app(): FastAPI, CORS, lifespan (фоновая загрузка графа)
│   ├── api/
│   │   ├── deps.py          DbSession, CurrentUser, require_roles, AppSettings
│   │   └── v1/
│   │       ├── router.py    сборка роутеров под префиксом /api/v1
│   │       └── endpoints/   health, auth, stats, reports, recommendations,
│   │                        branches, admin_users, admin_graph
│   ├── core/                config.py, security.py (JWT, bcrypt), graph_state.py
│   ├── db/                  models/ (users, branches, drivers, orders, report_templates), session.py
│   ├── repositories/        доступ к данным по таблицам
│   ├── schemas/             Pydantic-схемы запросов и ответов
│   ├── services/            auth, stats, report, routing_adapter, demand_adapter,
│   │                        graph_service, user_admin_service
│   ├── ml/                  ML-сервисы, визуализация (folium), генератор данных
│   └── scripts/seed.py      демо-данные + первый администратор
├── tests/                   pytest (SQLite in-memory, синтетический граф)
├── requirements.txt         рабочие зависимости (Python 3.12, версии зафиксированы)
└── requirements-dev.txt     + pytest, ruff, httpx
```

ER-диаграмма — [docs/er-diagram.md](../docs/er-diagram.md).

## 2. Быстрый старт

Нужен **Python 3.12** (на более новых версиях может не быть колёс pandas / scikit-learn /
osmnx) и PostgreSQL. Все команды — из **корня репозитория** (PowerShell).

```powershell
# 1. Окружение и зависимости
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt

# 2. PostgreSQL в Docker (логин/пароль/БД совпадают с DATABASE_URL по умолчанию)
docker run -d --name pizza-pg -e POSTGRES_USER=pizza -e POSTGRES_PASSWORD=pizza `
  -e POSTGRES_DB=pizza -p 5432:5432 postgres:16-alpine

# 3. Миграции
.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head

# 4. Демо-данные и первый администратор
$env:FIRST_ADMIN_USERNAME = "admin"
$env:FIRST_ADMIN_PASSWORD = "Admin12345"
.venv\Scripts\python.exe -m backend.app.scripts.seed
#  -> Создан администратор: admin
#  -> Филиалов: 7, водителей: 20, новых заказов: 1000, новых системных шаблонов отчётов: 4

# 5. Запуск API
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Вместо переменных окружения можно создать файл `.env` в корне репозитория:

```dotenv
DATABASE_URL=postgresql+psycopg://pizza:pizza@localhost:5432/pizza
JWT_SECRET_KEY=замените-на-длинную-случайную-строку
FIRST_ADMIN_USERNAME=admin
FIRST_ADMIN_PASSWORD=Admin12345
```

Что делает `seed` (идемпотентно, повторный запуск дублей не создаёт):

- 7 филиалов Нижнего Новгорода (с координатами и начальными очередями), 20 водителей
  (`Водитель 01` … `Водитель 20`, распределены по филиалам по кругу);
- заказы из `data/synthetic_orders.csv` (если файла нет — генерируется ML-генератором);
  время в CSV — местное (UTC+3), в БД сохраняется в UTC;
- 4 системных шаблона отчётов («Сводка по сети», «Нагрузка филиалов»,
  «Динамика заказов по дням», «Эффективность водителей»);
- первого администратора из `FIRST_ADMIN_*`, если администраторов в БД ещё нет.

После запуска:

| Адрес | Что это |
|---|---|
| http://localhost:8000/docs | Swagger UI (кнопка **Authorize** — вход логином/паролем) |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/openapi.json | OpenAPI-схема |
| http://localhost:8000/api/v1/health/ready | готовность БД и графа дорог |

Новая миграция после изменения моделей:
`.venv\Scripts\python.exe -m alembic -c backend/alembic.ini revision --autogenerate -m "описание"`.
URL БД для alembic можно переопределить: `alembic -c backend/alembic.ini -x db_url=... upgrade head`.

## 3. Настройки (переменные окружения)

Читаются из окружения и файла `.env` в корне (`backend/app/core/config.py`, `get_settings()`).
Неизвестные переменные игнорируются.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_NAME` | `NewFastPizza Analytics API` | Название (в `/health` и OpenAPI) |
| `APP_VERSION` | `0.1.0` | Версия (в `/health` и OpenAPI) |
| `API_V1_PREFIX` | `/api/v1` | Префикс всех эндпоинтов |
| `DATABASE_URL` | `postgresql+psycopg://pizza:pizza@localhost:5432/pizza` | Строка подключения SQLAlchemy (драйвер psycopg 3) |
| `JWT_SECRET_KEY` | `dev-only-insecure-jwt-secret-change-me-in-production` | Секрет подписи JWT. **В production обязательно задать**; с дефолтом в лог пишется предупреждение |
| `JWT_ALGORITHM` | `HS256` | Алгоритм подписи JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Срок жизни токена, мин (в ответе входа — `expires_in` в секундах) |
| `CORS_ORIGINS` | `http://localhost,http://localhost:5173` | Разрешённые origin: через запятую или JSON-массив (`["http://a","http://b"]`) |
| `DATA_DIR` | `<корень>/data` | Каталог данных (CSV заказов, граф) |
| `GRAPH_PATH` | `<DATA_DIR>/nn_graph.pkl` | Файл графа дорог (pickle `networkx.MultiDiGraph`) |
| `LOAD_GRAPH_ON_STARTUP` | `true` | Загружать граф в фоне при старте. При `false` маршруты отвечают 503, а `/health/ready` не считает граф обязательным |
| `GRAPH_DOWNLOAD_IF_MISSING` | `true` | Если файла графа нет — скачать из OpenStreetMap (несколько минут) и сохранить в `GRAPH_PATH` |
| `ROUTE_MAX_SNAP_DISTANCE_KM` | `2.0` | Точка водителя дальше этого расстояния от ближайшего узла графа — 422 |
| `GRAPH_UPLOAD_MAX_MB` | `100.0` | Лимит файла для `/admin/graph/upload` и `/admin/graph/weights`, МБ (больше — 413) |
| `FIRST_ADMIN_USERNAME` | — | Логин первого администратора (используется `seed`) |
| `FIRST_ADMIN_PASSWORD` | — | Пароль первого администратора |
| `FIRST_ADMIN_EMAIL` | — | Email первого администратора (необязательно) |
| `ALLOW_PUBLIC_REGISTRATION` | `true` | Разрешить `POST /auth/register`; при `false` — 403 |

## 4. Авторизация и роли

### Получение токена

JWT выдаёт `POST /api/v1/auth/login` по схеме **OAuth2 password flow**: тело —
`application/x-www-form-urlencoded` (не JSON!) с полями `username` и `password`.

```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin&password=Admin12345"
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIiwiaWF0IjoxNzkzNTYxMTcwLCJleHAiOjE3OTM1NjQ3NzB9.NN2fVstukpdB8xXvw9eO8SLOr156EZzK58pQIV202eQ",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Дальше токен передаётся в каждом запросе заголовком:

```
Authorization: Bearer <access_token>
```

В PowerShell удобно сохранить токен в переменную:

```powershell
$token = (Invoke-RestMethod -Method Post http://localhost:8000/api/v1/auth/login `
  -Body @{username="admin"; password="Admin12345"}).access_token
$H = @{Authorization = "Bearer $token"}
Invoke-RestMethod http://localhost:8000/api/v1/auth/me -Headers $H
```

Свойства токена:

- подпись `JWT_ALGORITHM` (HS256) ключом `JWT_SECRET_KEY`; полезная нагрузка — `sub`
  (id пользователя), `role`, `iat`, `exp`;
- срок жизни — `ACCESS_TOKEN_EXPIRE_MINUTES` (60 мин); refresh-токена нет — по истечении
  нужно снова вызвать `/auth/login`;
- пользователь **читается из БД на каждый запрос**: блокировка (`is_active=false`) и смена
  роли действуют сразу, без ожидания истечения токена (роль из токена не используется).

Ошибки авторизации:

| Ситуация | Код | Тело |
|---|---|---|
| Нет заголовка `Authorization` | 401 | `{"detail": "Not authenticated"}` |
| Токен неверный / просрочен / пользователь удалён | 401 | `{"detail": "Не удалось проверить учётные данные"}` |
| Неверный логин или пароль (`/auth/login`) | 401 | `{"detail": "Неверный логин или пароль"}` |
| Учётная запись заблокирована (вход или запрос с токеном) | 403 | `{"detail": "Учётная запись заблокирована"}` |
| Роль не подходит | 403 | `{"detail": "Недостаточно прав"}` |

Ответы 401 содержат заголовок `WWW-Authenticate: Bearer`.

### Роли

| Роль | Кто это |
|---|---|
| `admin` | Администратор: всё, включая пользователей и граф дорог |
| `manager` | Менеджер: статистика, свои шаблоны отчётов, очереди филиалов, рекомендации |
| `executive` | Руководство: статистика, чтение и экспорт отчётов, зоны спроса |
| `driver` | Водитель: рекомендация филиала, список филиалов |

Саморегистрация (`/auth/register`) всегда создаёт `driver`; другие роли назначает
администратор (`/admin/users`).

### Матрица доступа по эндпоинтам

«—» — 403, «публично» — токен не нужен.

| Эндпоинт | admin | manager | executive | driver |
|---|:-:|:-:|:-:|:-:|
| `GET /health`, `GET /health/ready` | публично | публично | публично | публично |
| `POST /auth/register`, `POST /auth/login` | публично | публично | публично | публично |
| `GET /auth/me` | ✓ | ✓ | ✓ | ✓ |
| `GET /stats/kpi`, `/stats/branch-load`, `/stats/timeseries` | ✓ | ✓ | ✓ | — |
| `GET /reports/templates` | все шаблоны | системные + свои | системные + свои | — |
| `GET /reports/templates/{id}`, `GET …/{id}/export.csv` | любой | системный или свой | системный или свой | — |
| `POST /reports/templates` | ✓ (в т.ч. `is_system=true`) | ✓ (только личный) | — | — |
| `PUT`/`DELETE /reports/templates/{id}` | любой | только свой личный | — | — |
| `POST /reports/preview`, `POST /reports/export.csv` | ✓ | ✓ | ✓ | — |
| `GET /recommendations/driver`, `/driver/map` | ✓ | ✓ | — | ✓ |
| `GET /recommendations/branches`, `/branches/map` | ✓ | ✓ | ✓ | — |
| `GET /branches` | ✓ | ✓ | ✓ | ✓ |
| `PATCH /branches/{id}/queue` | ✓ | ✓ | — | — |
| `/admin/users*` (все 5) | ✓ | — | — | — |
| `/admin/graph*` (все 4) | ✓ | — | — | — |

В коде роли проверяются зависимостью `require_roles(...)` (`backend/app/api/deps.py`);
права на конкретный шаблон — в `report_service` (`can_read`, `can_modify`, `can_create`).

## 5. Общие соглашения

- **Префикс** всех эндпоинтов — `/api/v1` (`API_V1_PREFIX`). Ниже пути указаны без него.
- **JSON** в UTF-8; кириллица не экранируется.
- **Даты и время** — ISO 8601, всегда **UTC**. В ответах — с суффиксом `Z`
  (`2026-10-01T00:00:00Z`). Во входных параметрах значение без часового пояса трактуется как
  UTC; можно передавать и просто дату (`2026-10-01` = `2026-10-01T00:00:00Z`) или время с
  поясом (`2026-10-01T03:00:00+03:00` — переводится в UTC).
- **Период** полуоткрытый: `date_from <= order_time < date_to`. Любая граница может
  отсутствовать (`null` — без ограничения). `date_from` позже `date_to` — 422.
- **Отсутствующие значения** — `null`, никогда `NaN` (например, среднее время доставки за
  период без доставок).
- **Доли** (`cancel_rate`) — число 0..1, 4 знака; **проценты** (`share_pct`, `deviation_pct`)
  — 0..100, 2 знака; **минуты** — 2 знака.
- **Повторяющиеся query-параметры** для списков: `?branch_id=1&branch_id=2`.

### Формат ошибок

Ошибки — стандартный формат FastAPI: объект с ключом `detail`.

Бизнес-ошибки (401/403/404/409/413/415/422/503) — `detail` строка:

```json
{"detail": "Шаблон не найден"}
```

Ошибки валидации запроса (422) — `detail` массив; `loc` — где ошибка (`body`/`query`/`path` +
путь к полю), `type` и `msg` — от Pydantic (на английском), `input` — полученное значение,
`ctx` — параметры ограничения (если есть). Реальный ответ `POST /auth/register` с телом
`{"username": "a b", "password": "short"}`:

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["body", "username"],
      "msg": "String should match pattern '^[A-Za-z0-9_.-]+$'",
      "input": "a b",
      "ctx": {"pattern": "^[A-Za-z0-9_.-]+$"}
    },
    {
      "type": "string_too_short",
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "input": "short",
      "ctx": {"min_length": 8}
    }
  ]
}
```

Исключение — `POST /admin/graph/upload` при непрошедшей проверке графа: `detail` — объект
`{"message": ..., "errors": [...]}` (см. [раздел 14](#post-admingraphupload)).

| Код | Когда |
|---|---|
| 200 / 201 / 204 | Успех / создано / удалено (без тела) |
| 401 | Нет токена, неверный или просроченный токен, неверный пароль |
| 403 | Недостаточно прав, учётная запись заблокирована, регистрация отключена |
| 404 | Объект не найден; нет маршрута; нет файла графа |
| 409 | Конфликт: логин/email/название шаблона заняты, защита администратора, водитель уже привязан, граф ещё загружается |
| 413 | Файл больше `GRAPH_UPLOAD_MAX_MB` |
| 415 | Неподдерживаемый формат файла графа (в т.ч. pickle) |
| 422 | Ошибка валидации; бизнес-проверки (период, точка вне графа, мало заказов, некорректный файл) |
| 500 | Не удалось сохранить граф на диск |
| 503 | Граф дорог не загружен (с заголовком `Retry-After`); `/health/ready` — сервис не готов |

## 6. Сводная таблица эндпоинтов

Всего **31** эндпоинт (совпадает с числом операций в `/openapi.json`).

| # | Метод | Путь | Роли | Назначение |
|---|---|---|---|---|
| 1 | GET | `/health` | публично | Liveness |
| 2 | GET | `/health/ready` | публично | Readiness: БД и граф |
| 3 | POST | `/auth/register` | публично | Саморегистрация (роль `driver`) |
| 4 | POST | `/auth/login` | публично | Вход, получение JWT |
| 5 | GET | `/auth/me` | любая | Текущий пользователь |
| 6 | GET | `/stats/kpi` | a, m, e | Сводные KPI за период |
| 7 | GET | `/stats/branch-load` | a, m, e | Нагрузка по филиалам |
| 8 | GET | `/stats/timeseries` | a, m, e | Временной ряд заказов |
| 9 | GET | `/reports/templates` | a, m, e | Список шаблонов |
| 10 | POST | `/reports/templates` | a, m | Создать шаблон |
| 11 | GET | `/reports/templates/{template_id}` | a, m, e | Шаблон по id |
| 12 | PUT | `/reports/templates/{template_id}` | a, m | Изменить шаблон |
| 13 | DELETE | `/reports/templates/{template_id}` | a, m | Удалить шаблон |
| 14 | GET | `/reports/templates/{template_id}/export.csv` | a, m, e | CSV по шаблону |
| 15 | POST | `/reports/preview` | a, m, e | Предпросмотр отчёта (JSON) |
| 16 | POST | `/reports/export.csv` | a, m, e | CSV ad-hoc отчёта |
| 17 | GET | `/recommendations/driver` | a, m, d | Лучший филиал для водителя |
| 18 | GET | `/recommendations/driver/map` | a, m, d | То же — HTML-карта |
| 19 | GET | `/recommendations/branches` | a, m, e | Зоны спроса K-Means |
| 20 | GET | `/recommendations/branches/map` | a, m, e | То же — HTML-карта |
| 21 | GET | `/branches` | все | Список филиалов |
| 22 | PATCH | `/branches/{branch_id}/queue` | a, m | Обновить очередь филиала |
| 23 | GET | `/admin/users` | a | Список пользователей |
| 24 | POST | `/admin/users` | a | Создать сотрудника |
| 25 | GET | `/admin/users/{user_id}` | a | Пользователь |
| 26 | PATCH | `/admin/users/{user_id}` | a | Изменить пользователя |
| 27 | DELETE | `/admin/users/{user_id}` | a | Деактивировать пользователя |
| 28 | GET | `/admin/graph/info` | a | Состояние графа |
| 29 | POST | `/admin/graph/weights` | a | Обновить веса рёбер (пробки) |
| 30 | POST | `/admin/graph/upload` | a | Загрузить новый граф |
| 31 | POST | `/admin/graph/reload` | a | Перечитать граф из `GRAPH_PATH` |

a — admin, m — manager, e — executive, d — driver.

---

## 7. health — состояние сервиса

### `GET /health`

Liveness: процесс жив и отвечает. Без авторизации, БД не трогает.

```powershell
curl.exe http://localhost:8000/api/v1/health
```

```json
{"status": "ok", "app": "NewFastPizza Analytics API", "version": "0.1.0"}
```

### `GET /health/ready`

Readiness: проверяет зависимости. Без авторизации.

- `database` — выполняется `SELECT 1`; при ошибке `status: "error"`, `detail` — имя класса
  исключения SQLAlchemy.
- `graph` — состояние графа в памяти: `ok` (загружен; `detail` — версия, число узлов и рёбер;
  при идущей перезагрузке добавляется «; идёт перезагрузка»), `loading`, `error`,
  `not_configured`.
- `required` — обязателен ли компонент. Граф обязателен только при
  `LOAD_GRAPH_ON_STARTUP=true`.
- Итог `not_ready` и **HTTP 503**, если обязательный компонент в `error` или `loading`;
  иначе `ready` и 200.

Ответ (200, граф загружен):

```json
{
  "status": "ready",
  "components": {
    "database": {"status": "ok", "detail": null, "required": true},
    "graph": {"status": "ok", "detail": "v1: 10732 узлов, 27374 рёбер", "required": true}
  }
}
```

`LOAD_GRAPH_ON_STARTUP=false` (200, граф необязателен):

```json
{
  "status": "ready",
  "components": {
    "database": {"status": "ok", "detail": null, "required": true},
    "graph": {
      "status": "not_configured",
      "detail": "Загрузка графа при старте отключена (LOAD_GRAPH_ON_STARTUP=false)",
      "required": false
    }
  }
}
```

Граф не загрузился (503):

```json
{
  "status": "not_ready",
  "components": {
    "database": {"status": "ok", "detail": null, "required": true},
    "graph": {
      "status": "error",
      "detail": "FileNotFoundError: Файл графа не найден: data/nn_graph.pkl",
      "required": true
    }
  }
}
```

Пока граф грузится — 503 с `"graph": {"status": "loading", "detail": "Граф загружается",
"required": true}` (по коду; на демо-графе 7 МБ загрузка занимает несколько секунд и вживую
не поймана).

## 8. auth — регистрация и вход

### `POST /auth/register`

Саморегистрация. Роль всегда `driver`. Тело — JSON (`UserRegister`):

| Поле | Тип | Обязательно | Ограничения |
|---|---|---|---|
| `username` | string | да | 3–64 символа, `^[A-Za-z0-9_.-]+$` |
| `password` | string | да | от 8 символов и не длиннее 72 байт (ограничение bcrypt) |
| `email` | string \| null | нет | до 255; приводится к нижнему регистру; `""` → `null` |
| `full_name` | string \| null | нет | до 255 |

```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" `
  -d '{\"username\":\"driver_self\",\"password\":\"Driver12345\",\"email\":\"Self@Example.com\",\"full_name\":\"Самостоятельный Водитель\"}'
```

Ответ **201** (`UserRead`; хеш пароля не отдаётся никогда):

```json
{
  "id": 2,
  "username": "driver_self",
  "email": "self@example.com",
  "full_name": "Самостоятельный Водитель",
  "role": "driver",
  "is_active": true,
  "created_at": "2026-11-01T19:26:10.757132Z"
}
```

Ошибки:

| Код | `detail` |
|---|---|
| 403 | `Публичная регистрация отключена` (`ALLOW_PUBLIC_REGISTRATION=false`) |
| 409 | `Пользователь с таким логином уже существует` / `Пользователь с таким email уже существует` |
| 422 | Валидация полей (пример — в [разделе 5](#формат-ошибок)) |

### `POST /auth/login`

Вход. Тело — **form-urlencoded** `username`, `password` (поля OAuth2 `grant_type`, `scope`,
`client_id`, `client_secret` допустимы, но не используются). Пример и ответ — в
[разделе 4](#получение-токена).

Внутри: поиск пользователя по логину, проверка bcrypt-хеша (для неизвестного логина тоже
выполняется проверка — время ответа не выдаёт существование логина), затем проверка
`is_active`.

| Код | `detail` |
|---|---|
| 401 | `Неверный логин или пароль` (+ `WWW-Authenticate: Bearer`) |
| 403 | `Учётная запись заблокирована` |
| 422 | Нет полей `username`/`password` в форме |

### `GET /auth/me`

Текущий пользователь по токену. Любая роль.

```powershell
curl.exe http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $token"
```

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "full_name": "Администратор",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-11-01T19:25:12.147180Z"
}
```

Ошибки: 401, 403 (заблокирован) — см. [раздел 4](#получение-токена).

## 9. stats — KPI и статистика

Роли: **admin, manager, executive** (driver — 403). Все три эндпоинта принимают общие
query-параметры:

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `date_from` | datetime | — | Начало периода, включительно (UTC) |
| `date_to` | datetime | — | Конец периода, не включительно (UTC) |
| `branch_id` | int, повторяемый | — | Фильтр по филиалам: `?branch_id=1&branch_id=2` (дубли убираются, список сортируется) |

В каждом ответе есть объект `period` — применённый фильтр (`date_from`, `date_to`,
`branch_ids`; `null` — без ограничения).

Как считается (`backend/app/services/stats_service.py`): заказы периода выгружаются одним
запросом в pandas DataFrame, метрики считаются векторно.

- `total_orders`/`orders` — все заказы периода (любого статуса);
- `delivered`, `canceled` — по статусам `Delivered`, `Canceled`;
- `cancel_rate` = `canceled / orders` (0..1);
- время доставки (`avg`/`median`/`p90_delivery_minutes`) — **только по доставленным**
  заказам с известным `delivery_time_minutes`; нет таких — `null`.

Ошибки (для всех трёх): 401, 403, 422 (`{"detail": "date_from должен быть не позже date_to"}`
или ошибка формата даты в массиве `detail`).

### `GET /stats/kpi`

Сводные KPI за период.

```powershell
curl.exe -H "Authorization: Bearer $token" `
  "http://localhost:8000/api/v1/stats/kpi?date_from=2026-10-01T00:00:00Z&date_to=2026-10-08T00:00:00Z&branch_id=1&branch_id=2"
```

```json
{
  "total_orders": 70,
  "delivered": 67,
  "canceled": 3,
  "cancel_rate": 0.0429,
  "avg_delivery_minutes": 38.67,
  "median_delivery_minutes": 42.0,
  "p90_delivery_minutes": 53.0,
  "period": {
    "date_from": "2026-10-01T00:00:00Z",
    "date_to": "2026-10-08T00:00:00Z",
    "branch_ids": [1, 2]
  }
}
```

Период без заказов (`?date_from=2020-01-01&date_to=2020-01-02`) — счётчики 0, средние `null`:

```json
{
  "total_orders": 0,
  "delivered": 0,
  "canceled": 0,
  "cancel_rate": 0.0,
  "avg_delivery_minutes": null,
  "median_delivery_minutes": null,
  "p90_delivery_minutes": null,
  "period": {"date_from": "2020-01-01T00:00:00Z", "date_to": "2020-01-02T00:00:00Z", "branch_ids": null}
}
```

Неверный тип (`?date_from=вчера`), 422:

```json
{
  "detail": [
    {
      "type": "datetime_from_date_parsing",
      "loc": ["query", "date_from"],
      "msg": "Input should be a valid datetime or date, invalid character in year",
      "input": "вчера",
      "ctx": {"error": "invalid character in year"}
    }
  ]
}
```

### `GET /stats/branch-load`

Нагрузка по филиалам. Активные филиалы показываются **и без заказов** (с нулями, участвуют в
средней); закрытые — только если у них есть заказы в периоде. Сортировка по `branch_id`.

Поля элемента `items`: `orders`, `share_pct` (доля заказов филиала от всех, %), `delivered`,
`canceled`, `cancel_rate`, `avg_delivery_minutes`, `deviation_from_mean` (отклонение числа
заказов от средней нагрузки на филиал, в заказах), `deviation_pct` (то же в %, `null` при
средней 0). `mean_orders` — средняя нагрузка на филиал.

```powershell
curl.exe -H "Authorization: Bearer $token" http://localhost:8000/api/v1/stats/branch-load
```

```json
{
  "period": {"date_from": null, "date_to": null, "branch_ids": null},
  "total_orders": 1000,
  "mean_orders": 142.86,
  "items": [
    {
      "branch_id": 1,
      "branch_name": "Филиал Нижегородский",
      "orders": 145,
      "share_pct": 14.5,
      "delivered": 134,
      "canceled": 11,
      "cancel_rate": 0.0759,
      "avg_delivery_minutes": 38.55,
      "deviation_from_mean": 2.14,
      "deviation_pct": 1.5
    },
    {
      "branch_id": 2,
      "branch_name": "Филиал Автозавод",
      "orders": 143,
      "share_pct": 14.3,
      "delivered": 132,
      "canceled": 11,
      "cancel_rate": 0.0769,
      "avg_delivery_minutes": 37.41,
      "deviation_from_mean": 0.14,
      "deviation_pct": 0.1
    },
    …
  ]
}
```

### `GET /stats/timeseries`

Временной ряд. Дополнительный параметр `granularity`: `hour` | `day` (по умолчанию) | `week`.
`period_start` — начало интервала в UTC; неделя начинается с понедельника. Интервалы между
первым и последним заказом без заказов заполняются нулями (`avg_delivery_minutes: null`),
чтобы график был непрерывным. Нет заказов — `points: []`.

```powershell
curl.exe -H "Authorization: Bearer $token" "http://localhost:8000/api/v1/stats/timeseries?granularity=week"
```

```json
{
  "period": {"date_from": null, "date_to": null, "branch_ids": null},
  "granularity": "week",
  "points": [
    {
      "period_start": "2026-09-28T00:00:00Z",
      "orders": 139,
      "delivered": 126,
      "canceled": 13,
      "cancel_rate": 0.0935,
      "avg_delivery_minutes": 36.52
    },
    {
      "period_start": "2026-10-05T00:00:00Z",
      "orders": 219,
      "delivered": 197,
      "canceled": 22,
      "cancel_rate": 0.1005,
      "avg_delivery_minutes": 37.98
    },
    …
  ]
}
```

Неверный шаг (`?granularity=month`), 422:

```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["query", "granularity"],
      "msg": "Input should be 'hour', 'day' or 'week'",
      "input": "month",
      "ctx": {"expected": "'hour', 'day' or 'week'"}
    }
  ]
}
```

## 10. reports — шаблоны, конструктор, CSV

Роли на уровне роутера: **admin, manager, executive** (driver — 403 на любой эндпоинт).
Права на конкретный шаблон:

- **системные** шаблоны (`is_system: true`, `owner_id: null`) читают и экспортируют все три
  роли; изменяет и удаляет только admin;
- **личные** шаблоны видит, меняет и удаляет только владелец или admin;
- executive — только чтение и экспорт (создать/изменить/удалить — 403);
- чужой личный шаблон для не-admin — **403** (не 404).

Название уникально среди системных шаблонов и среди личных шаблонов одного владельца — иначе 409.

### Конфигурация отчёта (`ReportConfig`)

Хранится в шаблоне (`config`) и передаётся в конструктор. Лишние поля запрещены (422).

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `metrics` | список, ≥ 1 | — | Метрики в порядке колонок (дубли удаляются): `orders`, `delivered`, `canceled`, `cancel_rate`, `avg_delivery_minutes`, `median_delivery_minutes`, `p90_delivery_minutes` |
| `group_by` | string \| null | `null` | Группировка: `branch`, `driver`, `status`, `hour`, `day`, `week`, `hour_of_day`, `weekday`; `null` — одна итоговая строка |
| `filters.branch_ids` | int[] \| null | `null` | Филиалы |
| `filters.driver_ids` | int[] \| null | `null` | Водители |
| `filters.statuses` | string[] \| null | `null` | Статусы: `Pending`, `InDelivery`, `Delivered`, `Canceled` |
| `default_period_days` | int \| null | `30` | 1..3650. Если в запросе не передан ни `date_from`, ни `date_to` — берутся последние N дней до текущего момента; `null` — вся история |

Списки фильтров дедуплицируются и сортируются; `null` или пустой список — без ограничения.
При `group_by: "branch"` после `branch_id` добавляется колонка `branch_name`, при `"driver"` —
`driver_name`. `weekday`: 0 — понедельник; `hour_of_day`: 0–23 (UTC).

Метрики считаются той же функцией `aggregate`, что и `/stats` (правила — в
[разделе 9](#9-stats--kpi-и-статистика)).

### Объект шаблона (`ReportTemplateRead`)

```json
{
  "id": 5,
  "name": "Мой отчёт по филиалам",
  "description": "Доставки по филиалам",
  "is_system": false,
  "owner_id": 3,
  "config": {
    "metrics": ["orders", "delivered", "avg_delivery_minutes"],
    "group_by": "branch",
    "filters": {"branch_ids": null, "driver_ids": null, "statuses": ["Canceled", "Delivered"]},
    "default_period_days": null
  },
  "created_at": "2026-11-01T19:26:13.036314Z",
  "updated_at": "2026-11-01T19:26:13.036314Z"
}
```

### `GET /reports/templates`

Список доступных шаблонов: сначала системные, затем личные, внутри — по названию.
admin видит все шаблоны всех пользователей; manager и executive — системные и свои.

```powershell
curl.exe -H "Authorization: Bearer $token" http://localhost:8000/api/v1/reports/templates
```

```json
[
  {
    "id": 3,
    "name": "Динамика заказов по дням",
    "description": "Количество заказов и время доставки по дням",
    "is_system": true,
    "owner_id": null,
    "config": {
      "metrics": ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"],
      "group_by": "day",
      "filters": {"branch_ids": null, "driver_ids": null, "statuses": null},
      "default_period_days": 30
    },
    "created_at": "2026-11-01T19:25:12.404078Z",
    "updated_at": "2026-11-01T19:25:12.404078Z"
  },
  {
    "id": 2,
    "name": "Нагрузка филиалов",
    "description": "Заказы, доставки, отмены и среднее время доставки по каждому филиалу",
    "is_system": true,
    "owner_id": null,
    "config": {
      "metrics": ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"],
      "group_by": "branch",
      "filters": {"branch_ids": null, "driver_ids": null, "statuses": null},
      "default_period_days": 30
    },
    "created_at": "2026-11-01T19:25:12.402557Z",
    "updated_at": "2026-11-01T19:25:12.402557Z"
  },
  …
]
```

Системные шаблоны после `seed`:

| id | Название | `group_by` | Метрики |
|---|---|---|---|
| 1 | Сводка по сети | `null` | все 7 |
| 2 | Нагрузка филиалов | `branch` | orders, delivered, canceled, cancel_rate, avg_delivery_minutes |
| 3 | Динамика заказов по дням | `day` | orders, delivered, canceled, cancel_rate, avg_delivery_minutes |
| 4 | Эффективность водителей | `driver` | orders, delivered, cancel_rate, avg, median, p90 delivery_minutes |

(id — при seed в пустую БД.)

### `POST /reports/templates`

Создать шаблон. admin и manager; `is_system: true` — только admin (manager получит 403).
Владелец личного шаблона — текущий пользователь.

Тело (`ReportTemplateCreate`): `name` (1–255, обяз.), `description` (до 2000, опц.),
`config` (`ReportConfig`, обяз.), `is_system` (bool, `false`).

```powershell
curl.exe -X POST http://localhost:8000/api/v1/reports/templates -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{\"name\":\"Мой отчёт по филиалам\",\"description\":\"Доставки по филиалам\",\"config\":{\"metrics\":[\"orders\",\"delivered\",\"avg_delivery_minutes\"],\"group_by\":\"branch\",\"filters\":{\"statuses\":[\"Delivered\",\"Canceled\"]},\"default_period_days\":null}}'
```

Ответ **201** — объект шаблона (см. пример выше).

| Код | `detail` |
|---|---|
| 403 | `Недостаточно прав` (executive; manager с `is_system: true`) |
| 409 | `Шаблон с таким названием уже существует` |
| 422 | Неизвестная метрика / группировка, пустой `metrics`, лишнее поле |

Пример 422 (`"metrics": ["revenue"], "group_by": "month"`):

```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["body", "config", "metrics", 0],
      "msg": "Input should be 'orders', 'delivered', 'canceled', 'cancel_rate', 'avg_delivery_minutes', 'median_delivery_minutes' or 'p90_delivery_minutes'",
      "input": "revenue",
      "ctx": {"expected": "'orders', 'delivered', 'canceled', 'cancel_rate', 'avg_delivery_minutes', 'median_delivery_minutes' or 'p90_delivery_minutes'"}
    },
    {
      "type": "literal_error",
      "loc": ["body", "config", "group_by"],
      "msg": "Input should be 'branch', 'driver', 'status', 'hour', 'day', 'week', 'hour_of_day' or 'weekday'",
      "input": "month",
      "ctx": {"expected": "'branch', 'driver', 'status', 'hour', 'day', 'week', 'hour_of_day' or 'weekday'"}
    }
  ]
}
```

### `GET /reports/templates/{template_id}`

Шаблон по id. Ответ 200 — объект шаблона. Ошибки: 404 `Шаблон не найден`, 403 `Недостаточно
прав` (чужой личный шаблон).

### `PUT /reports/templates/{template_id}`

Полная замена `name`, `description`, `config` (тело `ReportTemplateUpdate` — те же поля, что
при создании, без `is_system`; признак системности и владелец не меняются). Право: владелец
личного шаблона или admin; системный — только admin.

```powershell
curl.exe -X PUT http://localhost:8000/api/v1/reports/templates/5 -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{\"name\":\"Мой отчёт по филиалам\",\"description\":\"Отмены по филиалам\",\"config\":{\"metrics\":[\"orders\",\"canceled\",\"cancel_rate\"],\"group_by\":\"branch\",\"filters\":{\"statuses\":[\"Delivered\",\"Canceled\"]},\"default_period_days\":null}}'
```

```json
{
  "id": 5,
  "name": "Мой отчёт по филиалам",
  "description": "Отмены по филиалам",
  "is_system": false,
  "owner_id": 3,
  "config": {
    "metrics": ["orders", "canceled", "cancel_rate"],
    "group_by": "branch",
    "filters": {"branch_ids": null, "driver_ids": null, "statuses": ["Canceled", "Delivered"]},
    "default_period_days": null
  },
  "created_at": "2026-11-01T19:26:13.036314Z",
  "updated_at": "2026-11-01T19:26:13.080487Z"
}
```

Ошибки: 403, 404, 409, 422.

### `DELETE /reports/templates/{template_id}`

Удаление (физическое). Ответ **204** без тела. Права — как у `PUT`. Ошибки: 403, 404.

### `GET /reports/templates/{template_id}/export.csv`

Строит отчёт по конфигурации шаблона и отдаёт CSV-файл.

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `date_from` | datetime | — | Начало периода (UTC) |
| `date_to` | datetime | — | Конец периода (UTC), не включительно |
| `delimiter` | `;` \| `,` | `;` | Разделитель CSV (в URL `;` можно передать как `%3B`) |

Если ни одна дата не передана — период из `config.default_period_days` (последние N дней).

```powershell
curl.exe -H "Authorization: Bearer $token" -OJ `
  "http://localhost:8000/api/v1/reports/templates/3/export.csv?date_from=2026-10-01&date_to=2026-10-04"
```

Заголовки ответа:

```
content-type: text/csv; charset=utf-8
content-disposition: attachment; filename="report_2026-10-01_2026-10-04.csv"; filename*=UTF-8''report_%D0%B4%D0%B8%D0%BD%D0%B0%D0%BC%D0%B8%D0%BA%D0%B0_%D0%B7%D0%B0%D0%BA%D0%B0%D0%B7%D0%BE%D0%B2_%D0%BF%D0%BE_%D0%B4%D0%BD%D1%8F%D0%BC_2026-10-01_2026-10-04.csv
```

Тело — см. [формат CSV](#формат-csv). Ошибки: 403, 404, 422.

### `POST /reports/preview`

Конструктор: конфигурация + период → строки отчёта в JSON (для таблицы/графика на фронте).

Тело (`ReportRequest`): `config` (`ReportConfig`, обяз.), `date_from`, `date_to` (опц.),
`name` (1–255, по умолчанию `adhoc`; для preview не используется).

```powershell
curl.exe -X POST http://localhost:8000/api/v1/reports/preview -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{\"config\":{\"metrics\":[\"orders\",\"delivered\",\"cancel_rate\",\"avg_delivery_minutes\",\"p90_delivery_minutes\"],\"group_by\":\"weekday\"},\"date_from\":\"2026-10-01T00:00:00Z\",\"date_to\":\"2026-11-01T00:00:00Z\"}'
```

```json
{
  "period": {"date_from": "2026-10-01T00:00:00Z", "date_to": "2026-11-01T00:00:00Z"},
  "columns": [
    {"key": "weekday", "label": "День недели (0 = пн)"},
    {"key": "orders", "label": "Заказов"},
    {"key": "delivered", "label": "Доставлено"},
    {"key": "cancel_rate", "label": "Доля отмен"},
    {"key": "avg_delivery_minutes", "label": "Среднее время доставки, мин"},
    {"key": "p90_delivery_minutes", "label": "90-й перцентиль времени доставки, мин"}
  ],
  "rows": [
    {"weekday": 0, "orders": 122, "delivered": 113, "cancel_rate": 0.0738, "avg_delivery_minutes": 36.22, "p90_delivery_minutes": 56.0},
    {"weekday": 1, "orders": 131, "delivered": 119, "cancel_rate": 0.0916, "avg_delivery_minutes": 38.5, "p90_delivery_minutes": 57.0},
    {"weekday": 2, "orders": 145, "delivered": 134, "cancel_rate": 0.0759, "avg_delivery_minutes": 37.72, "p90_delivery_minutes": 57.0},
    …
  ]
}
```

- `period` — **фактический** период: без дат и с `default_period_days: 30` в ответе будут
  вычисленные границы, например
  `{"date_from": "2026-10-02T19:26:13.156521Z", "date_to": "2026-11-01T19:26:13.156521Z"}`.
- `columns[].key` — ключи в `rows`, `label` — русские заголовки (как в CSV).
- Группировка по водителю (`"group_by": "driver"`) добавляет `driver_name`:
  `{"driver_id": 1, "driver_name": "Водитель 01", "orders": 11, "delivered": 11, "avg_delivery_minutes": 42.73}`.
- Время в строках с `group_by` `hour`/`day`/`week` — ISO 8601 UTC.

Ошибки: 403, 422 (валидация `config`, `date_from` позже `date_to`). Пример 422 при пустом
`metrics`:

```json
{
  "detail": [
    {
      "type": "too_short",
      "loc": ["body", "config", "metrics"],
      "msg": "List should have at least 1 item after validation, not 0",
      "input": [],
      "ctx": {"field_type": "List", "min_length": 1, "actual_length": 0}
    }
  ]
}
```

### `POST /reports/export.csv`

То же тело, что у `/reports/preview`, но ответ — CSV-файл. `name` идёт в имя файла.
Query-параметр `delimiter` (`;` по умолчанию или `,`).

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/reports/export.csv" -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -OJ `
  -d '{\"name\":\"Отчёт по дням\",\"config\":{\"metrics\":[\"orders\",\"cancel_rate\",\"avg_delivery_minutes\"],\"group_by\":\"day\"},\"date_from\":\"2026-10-01\",\"date_to\":\"2026-10-04\"}'
```

Заголовок: `content-disposition: attachment; filename="report_2026-10-01_2026-10-04.csv";
filename*=UTF-8''report_%D0%BE%D1%82%D1%87%D1%91%D1%82_%D0%BF%D0%BE_%D0%B4%D0%BD%D1%8F%D0%BC_2026-10-01_2026-10-04.csv`.

```csv
День (UTC);Заказов;Доля отмен;Среднее время доставки, мин
2026-10-01;34;0,0882;32,13
2026-10-02;25;0,12;37,55
2026-10-03;34;0,1471;35,79
```

Ошибки: 403, 422.

### Формат CSV

| Свойство | Значение |
|---|---|
| Кодировка | UTF-8 **с BOM** (`EF BB BF`) — Excel сразу распознаёт кириллицу |
| Разделитель | `;` (по умолчанию, Excel RU) или `,` (`?delimiter=,`) |
| Десятичный разделитель | при `;` — запятая (`0,0882`), при `,` — точка (`0.0882`) |
| Строки | CRLF (`\r\n`); значения с разделителем берутся в кавычки |
| Заголовки | русские (см. таблицу ниже) |
| Пустые значения | пустая ячейка |
| Время | `hour` — `YYYY-MM-DD HH:MM`, `day`/`week` — `YYYY-MM-DD` (UTC) |
| Имя файла | `report_<slug названия>_<from>_<to>.csv`; открытые границы — `start` / `now`. В `filename*` (RFC 5987) — полное имя с кириллицей, в `filename` — ASCII-запасной вариант без кириллических частей |

Заголовки колонок:

| Ключ | Заголовок CSV | Ключ | Заголовок CSV |
|---|---|---|---|
| `branch_id` | ID филиала | `orders` | Заказов |
| `branch_name` | Филиал | `delivered` | Доставлено |
| `driver_id` | ID водителя | `canceled` | Отменено |
| `driver_name` | Водитель | `cancel_rate` | Доля отмен |
| `status` | Статус | `avg_delivery_minutes` | Среднее время доставки, мин |
| `hour` | Час (UTC) | `median_delivery_minutes` | Медиана времени доставки, мин |
| `day` | День (UTC) | `p90_delivery_minutes` | 90-й перцентиль времени доставки, мин |
| `week` | Неделя с (UTC) | `hour_of_day` | Час суток (UTC) |
| `weekday` | День недели (0 = пн) | | |

Пример — шаблон «Нагрузка филиалов» с `?delimiter=,&date_from=2026-10-01&date_to=2026-11-01`:

```csv
ID филиала,Филиал,Заказов,Доставлено,Отменено,Доля отмен,"Среднее время доставки, мин"
1,Филиал Нижегородский,142,131,11,0.0775,38.48
2,Филиал Автозавод,143,132,11,0.0769,37.41
3,Филиал Сормово,139,127,12,0.0863,37.02
…
```

То же с разделителем `;` (по умолчанию) — личный шаблон с метриками orders, canceled,
cancel_rate:

```csv
ID филиала;Филиал;Заказов;Отменено;Доля отмен
1;Филиал Нижегородский;145;11;0,0759
2;Филиал Автозавод;143;11;0,0769
3;Филиал Сормово;140;12;0,0857
…
```

## 11. recommendations — рекомендации

Эндпоинты синхронные: FastAPI выполняет их в пуле потоков, поэтому Дейкстра, K-Means и
генерация карт не блокируют event loop.

### `GET /recommendations/driver`

Лучший филиал для водителя по графу дорог и очередям. Роли: **admin, manager, driver**.

| Параметр | Тип | Ограничения | Описание |
|---|---|---|---|
| `lat` | float | -90..90, обяз. | Широта водителя |
| `lon` | float | -180..180, обяз. | Долгота водителя |

Как работает (`backend/app/services/routing_adapter.py`, `FastRoutingService` — подкласс
ML-`RoutingService`):

1. Берётся текущий снимок графа из памяти (нет графа — 503).
2. Активные филиалы и их очереди читаются из БД на каждый запрос (изменение очереди через
   `PATCH /branches/{id}/queue` учитывается сразу).
3. Ближайший к водителю узел ищется по BallTree (haversine), построенному один раз при
   загрузке графа. Дальше `ROUTE_MAX_SNAP_DISTANCE_KM` (2 км) — 422.
4. Узлы филиалов кэшируются в снимке графа.
5. **Один** проход Дейкстры от узла водителя по весу `travel_time` (секунды), с остановкой,
   когда достигнуты все узлы филиалов.
6. Выбирается филиал с минимальной оценкой `score = минуты_в_пути − очередь × 2`
   (меньше — лучше: большая очередь означает, что заказы ждут водителя). Недостижимые филиалы
   пропускаются; ни один не достижим — 404.

```powershell
curl.exe -H "Authorization: Bearer $token" "http://localhost:8000/api/v1/recommendations/driver?lat=56.30&lon=43.98"
```

```json
{
  "branch_id": 6,
  "branch_name": "Филиал Канавинский",
  "travel_time_minutes": 7.3,
  "queue_size": 6,
  "score": -4.7,
  "driver_node": 1656796928,
  "branch_node": 8768887639,
  "route": [
    [56.300433, 43.9790447],
    [56.3006155, 43.9790654],
    [56.3007062, 43.9790909],
    …
  ],
  "graph_version": 1,
  "elapsed_ms": 24.1
}
```

| Поле | Описание |
|---|---|
| `travel_time_minutes` | Время в пути по графу, мин (1 знак) |
| `queue_size` | Текущая очередь филиала |
| `score` | `travel_time_minutes − queue_size × 2` |
| `driver_node`, `branch_node` | id узлов графа (OSM id — int; в загруженных графах могут быть строками) |
| `route` | Маршрут — точки `[lat, lon]` от водителя до филиала (в примере 46 точек) |
| `graph_version` | Версия графа, на которой посчитан ответ (растёт при каждой замене) |
| `elapsed_ms` | Время расчёта на сервере |

Ошибки:

| Код | `detail` |
|---|---|
| 403 | `Недостаточно прав` (executive) |
| 404 | `Нет маршрута ни к одному активному филиалу` (в т.ч. нет активных филиалов) |
| 422 | `Точка в 385.1 км от ближайшей дороги графа (допустимо не более 2 км)` |
| 422 | Координаты вне диапазона — массив `detail` (`less_than_equal`, `loc: ["query", "lat"]`) |
| 503 | Граф не загружен — см. [раздел 15](#15-граф-дорог-жизненный-цикл) |

### `GET /recommendations/driver/map`

То же, но ответ — **HTML-страница** (`text/html; charset=utf-8`) с картой folium/Leaflet:
маршрут водителя, все филиалы и заказы (генератор ML-части `MapGenerator`). Параметры, роли
и ошибки — как у `/recommendations/driver`. Карта строится во временном каталоге и после
чтения удаляется; если генератор ничего не построил — 404 `Карта не построена`.

```powershell
curl.exe -H "Authorization: Bearer $token" -o route.html "http://localhost:8000/api/v1/recommendations/driver/map?lat=56.30&lon=43.98"
```

Начало ответа:

```html
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8" />
    <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
    …
```

Для встраивания на фронте — `<iframe srcdoc>` или blob-URL (нужен заголовок авторизации,
поэтому прямой `src` не подойдёт).

### `GET /recommendations/branches`

Зоны спроса и вердикт по филиалам (K-Means по координатам **доставленных** заказов периода).
Роли: **admin, manager, executive**.

| Параметр | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `n_clusters` | int | `7` | 1..50 | Число кластеров (зон) |
| `date_from` | datetime | — | | Начало периода (UTC) |
| `date_to` | datetime | — | строго позже `date_from` | Конец периода (UTC), не включительно |
| `coverage_radius_km` | float | `2.0` | > 0, ≤ 50 | Радиус «рядом есть филиал» |
| `high_demand_threshold` | int | `130` | ≥ 0 | Порог высокого спроса (заказов в зоне) |
| `low_demand_threshold` | int | `80` | ≥ 0 | Порог низкого спроса |

Как работает (`demand_adapter.PeriodKMeansAnalyzer` → ML-`KMeansAnalyzer`): доставленные
заказы периода кластеризуются на `n_clusters` зон; для каждого центра ищется ближайший
активный филиал (haversine) и выносится рекомендация:

| Филиал в радиусе `coverage_radius_km`? | Заказов в зоне | `recommendation` |
|---|---|---|
| нет | ≥ `high_demand_threshold` | `Открыть филиал` |
| нет | < `high_demand_threshold` | `Спрос низкий` |
| да | < `low_demand_threshold` | `Закрыть филиал` |
| да | ≥ `low_demand_threshold` | `Филиал рентабелен` |

```powershell
curl.exe -H "Authorization: Bearer $token" `
  "http://localhost:8000/api/v1/recommendations/branches?n_clusters=3&date_from=2026-10-01&date_to=2026-10-08"
```

```json
{
  "n_clusters": 3,
  "date_from": "2026-10-01T00:00:00Z",
  "date_to": "2026-10-08T00:00:00Z",
  "orders_count": 206,
  "zones": [
    {
      "zone_id": 0,
      "center_lat": 56.277938,
      "center_lon": 43.884554,
      "order_count": 70,
      "recommendation": "Спрос низкий",
      "nearest_branch_id": 2,
      "nearest_branch_name": "Филиал Автозавод",
      "distance_to_branch_km": 4.33
    },
    {
      "zone_id": 1,
      "center_lat": 56.363035,
      "center_lon": 43.824745,
      "order_count": 46,
      "recommendation": "Закрыть филиал",
      "nearest_branch_id": 3,
      "nearest_branch_name": "Филиал Сормово",
      "distance_to_branch_km": 0.51
    },
    {
      "zone_id": 2,
      "center_lat": 56.294086,
      "center_lon": 44.010465,
      "order_count": 90,
      "recommendation": "Филиал рентабелен",
      "nearest_branch_id": 7,
      "nearest_branch_name": "Филиал Советский",
      "distance_to_branch_km": 0.23
    }
  ],
  "elapsed_ms": 17.7
}
```

`orders_count` — число доставленных заказов периода; `nearest_branch_*` и
`distance_to_branch_km` — `null`, если активных филиалов нет. Граф дорог не нужен.

Ошибки:

| Код | `detail` |
|---|---|
| 403 | `Недостаточно прав` (driver) |
| 422 | `Недостаточно доставленных заказов для кластеризации: 0 при n_clusters=10. Расширьте период или уменьшите n_clusters.` |
| 422 | `date_from должен быть раньше date_to` (здесь равенство тоже ошибка) |
| 422 | Параметры вне диапазона — массив `detail` |

### `GET /recommendations/branches/map`

HTML-карта (folium): тепловая карта заказов, филиалы и центроиды K-Means за тот же период
(`ClustersMapGenerator`). Параметры, роли и ошибки — как у `/recommendations/branches`.

## 12. branches — филиалы и очереди

### `GET /branches`

Список филиалов, сортировка по id. Роли: **все четыре** (водителю нужен список и очереди).

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `include_inactive` | bool | `false` | Включить закрытые филиалы (`is_active=false`) |

```powershell
curl.exe -H "Authorization: Bearer $token" http://localhost:8000/api/v1/branches
```

```json
[
  {"id": 1, "name": "Филиал Нижегородский", "lat": 56.322974, "lon": 44.034741, "current_queue": 5, "is_active": true},
  {"id": 2, "name": "Филиал Автозавод", "lat": 56.241094, "lon": 43.861618, "current_queue": 1, "is_active": true},
  {"id": 3, "name": "Филиал Сормово", "lat": 56.364246, "lon": 43.816756, "current_queue": 4, "is_active": true},
  …
]
```

### `PATCH /branches/{branch_id}/queue`

Обновить текущую очередь заказов филиала. Роли: **admin, manager**. Новое значение сразу
учитывается в `/recommendations/driver`.

Тело: `{"current_queue": <int 0..10000>}`.

```powershell
curl.exe -X PATCH http://localhost:8000/api/v1/branches/7/queue -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -d '{\"current_queue\": 3}'
```

```json
{"id": 7, "name": "Филиал Советский", "lat": 56.293337, "lon": 44.013856, "current_queue": 3, "is_active": true}
```

Ошибки: 403 (executive, driver), 404 `Филиал не найден`, 422 (например `current_queue: -1` →
`greater_than_equal`, `loc: ["body", "current_queue"]`).

## 13. admin/users — пользователи

Только **admin** (остальные роли — 403 `Недостаточно прав`).

Объект пользователя в админке (`UserAdminRead`) — поля `UserRead` плюс `updated_at` и
`driver_id` (id связанной записи в таблице `drivers` — водитель из заказов; `null` — не
привязан):

```json
{
  "id": 5,
  "username": "driver1",
  "email": null,
  "full_name": "Пётр Водитель",
  "role": "driver",
  "is_active": true,
  "created_at": "2026-11-01T19:26:11.466445Z",
  "updated_at": "2026-11-01T19:26:11.466445Z",
  "driver_id": 1
}
```

**Защита администратора** (409): нельзя деактивировать или понизить **себя** и нельзя
деактивировать/понизить **последнего активного** администратора (проверка блокирует строки
активных админов, чтобы два параллельных запроса не обошли её).

### `GET /admin/users`

Список с пагинацией, сортировка по id.

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `role` | `admin`\|`manager`\|`executive`\|`driver` | — | Фильтр по роли |
| `is_active` | bool | — | Фильтр по активности |
| `search` | string, ≤ 100 | — | Подстрока логина или ФИО, без учёта регистра (`%` и `_` ищутся буквально) |
| `limit` | int 1..200 | `50` | Размер страницы |
| `offset` | int ≥ 0 | `0` | Смещение |

```powershell
curl.exe -H "Authorization: Bearer $token" "http://localhost:8000/api/v1/admin/users?limit=3"
```

```json
{
  "items": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "full_name": "Администратор",
      "role": "admin",
      "is_active": true,
      "created_at": "2026-11-01T19:25:12.147180Z",
      "updated_at": "2026-11-01T19:25:12.147180Z",
      "driver_id": null
    },
    {
      "id": 2,
      "username": "driver_self",
      "email": "self@example.com",
      "full_name": "Самостоятельный Водитель",
      "role": "driver",
      "is_active": true,
      "created_at": "2026-11-01T19:26:10.757132Z",
      "updated_at": "2026-11-01T19:26:10.757132Z",
      "driver_id": null
    },
    …
  ],
  "total": 5,
  "limit": 3,
  "offset": 0
}
```

`total` — число записей с учётом фильтров (без пагинации).

### `POST /admin/users`

Создать сотрудника с любой ролью. Тело (`UserCreate`) — поля регистрации
(`username`, `password`, `email`, `full_name` с теми же ограничениями) плюс:

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `role` | `admin`\|`manager`\|`executive`\|`driver` | обяз. | Роль |
| `is_active` | bool | `true` | Активность |
| `driver_id` | int \| null | `null` | Привязать к записи водителя (только для роли `driver`) |

```powershell
curl.exe -X POST http://localhost:8000/api/v1/admin/users -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"manager1\",\"password\":\"Manager12345\",\"role\":\"manager\",\"full_name\":\"Мария Менеджер\",\"email\":\"manager1@example.com\"}'
```

Ответ **201**:

```json
{
  "id": 3,
  "username": "manager1",
  "email": "manager1@example.com",
  "full_name": "Мария Менеджер",
  "role": "manager",
  "is_active": true,
  "created_at": "2026-11-01T19:26:11.070426Z",
  "updated_at": "2026-11-01T19:26:11.070426Z",
  "driver_id": null
}
```

| Код | `detail` |
|---|---|
| 404 | `Водитель не найден` (нет записи `drivers` с таким `driver_id`) |
| 409 | `Пользователь с таким логином уже существует` / `... email уже существует` |
| 409 | `Водитель уже привязан к другой учётной записи` |
| 422 | `Привязать запись водителя можно только к роли driver` |
| 422 | Валидация полей — массив `detail` |

### `GET /admin/users/{user_id}`

Пользователь по id (`UserAdminRead`). Ошибка: 404 `Пользователь не найден`.

### `PATCH /admin/users/{user_id}`

Частичное изменение: передаются только меняемые поля; лишние поля — 422 (`extra_forbidden`).

| Поле | Тип | Семантика |
|---|---|---|
| `role` | роль | Сменить роль (`null` — не менять). Смена с `driver` на другую роль автоматически отвязывает запись водителя |
| `full_name` | string \| null | Новое ФИО; `null` — очистить |
| `email` | string \| null | Новый email; `null` или `""` — очистить |
| `is_active` | bool | Блокировка/разблокировка (`null` — не менять) |
| `password` | string | Сброс пароля (те же правила, что при регистрации; `null` — не менять) |
| `driver_id` | int \| null | Привязать к записи водителя; `null` — отвязать |

```powershell
curl.exe -X PATCH http://localhost:8000/api/v1/admin/users/4 -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -d '{\"full_name\":\"Иван Петрович\",\"email\":\"exec1@example.com\"}'
```

```json
{
  "id": 4,
  "username": "exec1",
  "email": "exec1@example.com",
  "full_name": "Иван Петрович",
  "role": "executive",
  "is_active": true,
  "created_at": "2026-11-01T19:26:11.270304Z",
  "updated_at": "2026-11-01T19:26:12.671879Z",
  "driver_id": null
}
```

Ошибки: 404, 409 (email занят, защита администратора, водитель занят), 422. Пример лишнего
поля (`{"foo": 1}`):

```json
{"detail": [{"type": "extra_forbidden", "loc": ["body", "foo"], "msg": "Extra inputs are not permitted", "input": 1}]}
```

### `DELETE /admin/users/{user_id}`

**Мягкое** удаление: `is_active=false`, данные и история сохраняются. Ответ 200 — объект
пользователя:

```json
{
  "id": 4,
  "username": "exec1",
  "email": "exec1@example.com",
  "full_name": "Иван Петрович",
  "role": "executive",
  "is_active": false,
  "created_at": "2026-11-01T19:26:11.270304Z",
  "updated_at": "2026-11-01T19:26:12.683637Z",
  "driver_id": null
}
```

После этого вход и любые запросы с ранее выданным токеном — 403 `Учётная запись
заблокирована`. Вернуть доступ — `PATCH /admin/users/{id}` с `{"is_active": true}`.

Ошибки: 404, 409 (`Нельзя деактивировать или понизить собственную учётную запись`,
`Нельзя деактивировать или понизить последнего администратора`).

## 14. admin/graph — граф дорог

Только **admin**. Все изменения выполняются по одной схеме под общей блокировкой
(`GraphRegistry.mutation_lock` — параллельные изменения идут по очереди):

1. правка **копии** текущего графа (или разбор загруженного файла) и проверка;
2. атомарная запись pickle в `GRAPH_PATH` (временный файл в том же каталоге → fsync →
   `os.replace`); ошибка записи — 500, в памяти остаётся прежний граф;
3. подмена графа в памяти (`replace_graph`): новый BallTree, пересчёт кэша узлов филиалов,
   `version + 1`. Запросы маршрутов, начатые до замены, досчитываются на старом снимке.

Пока граф грузится при старте — любое изменение 409 `Граф загружается при старте — повторите
позже`. Файл больше `GRAPH_UPLOAD_MAX_MB` — 413 `Файл больше допустимых 100 МБ`; пустой файл
— 422 `Пустой файл`.

### Объект состояния графа (`GraphInfo`)

| Поле | Описание |
|---|---|
| `status` | `not_loaded` / `loading` / `ready` / `failed` |
| `error` | Текст последней ошибки загрузки или `null` |
| `version` | Версия графа в памяти (1 — первая загрузка, далее +1 на каждую замену) |
| `source` | Откуда граф: путь к файлу, `weights:<имя файла>`, `upload:<имя файла>` |
| `nodes`, `edges` | Число узлов и рёбер |
| `loaded_at` | Когда загружен текущий граф (UTC) |
| `bbox` | Границы графа: `min_lat`, `min_lon`, `max_lat`, `max_lon` |
| `branch_nodes_cached` | Сколько координат филиалов закэшировано (узлы считаются при первом запросе маршрута) |
| `graph_path` | `GRAPH_PATH` |
| `file_exists`, `file_size_bytes`, `file_modified_at` | Состояние файла на диске |
| `upload_max_mb` | Лимит загрузки, МБ |

Поля графа (`version`…`branch_nodes_cached`) — `null`, пока граф не загружен.

### `GET /admin/graph/info`

```powershell
curl.exe -H "Authorization: Bearer $token" http://localhost:8000/api/v1/admin/graph/info
```

```json
{
  "status": "ready",
  "error": null,
  "version": 1,
  "source": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
  "nodes": 10732,
  "edges": 27374,
  "loaded_at": "2026-11-01T19:25:20.959122Z",
  "bbox": {"min_lat": 56.1852248, "min_lon": 43.7568534, "max_lat": 56.4544954, "max_lon": 44.2411582},
  "branch_nodes_cached": 0,
  "graph_path": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
  "file_exists": true,
  "file_size_bytes": 6935536,
  "file_modified_at": "2026-11-01T19:25:09.381546Z",
  "upload_max_mb": 100.0
}
```

(Во всех примерах этого раздела `source` и `graph_path` заменены на путь по умолчанию: при
съёмке сервер работал на временной копии графа. Остальные значения — реальные.)

Граф не загрузился:

```json
{
  "status": "failed",
  "error": "FileNotFoundError: Файл графа не найден: data/nn_graph.pkl",
  "version": null,
  "source": null,
  "nodes": null,
  "edges": null,
  "loaded_at": null,
  "bbox": null,
  "branch_nodes_cached": null,
  "graph_path": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
  "file_exists": false,
  "file_size_bytes": null,
  "file_modified_at": null,
  "upload_max_mb": 100.0
}
```

### `POST /admin/graph/weights`

Обновить веса рёбер (пробки). `multipart/form-data`, поле `file` — CSV или JSON.

Каждая строка: `u`, `v` (id узлов), необязательный `key` (без него — **все** параллельные
рёбра `u→v`) и **ровно одно** из:

- `travel_time` — новое время проезда ребра, секунды (> 0);
- `multiplier` — множитель (> 0) к **исходному** времени без пробок. Исходное значение
  запоминается в атрибуте `travel_time_base` при первом изменении, поэтому множители не
  накапливаются: `3` и затем `1` — снова исходное время.

**CSV**: UTF-8 (BOM допускается), заголовок обязателен, колонки `u`, `v` и `travel_time`
и/или `multiplier` (`key` — опционально), регистр не важен; разделитель `,` или `;`
(определяется по заголовку).

```csv
u,v,key,multiplier,travel_time
244888032,2497168540,,3,
244888032,2497168540,0,,45.5
```

**JSON**: массив объектов или объект с массивом `rows` (или `edges`):

```json
{"rows": [{"u": 244888032, "v": 2497168540, "multiplier": 1}]}
```

Некорректные строки **пропускаются** с указанием причины; граф заменяется и сохраняется, если
обновлено хотя бы одно ребро.

```powershell
curl.exe -H "Authorization: Bearer $token" -F "file=@jam.csv" http://localhost:8000/api/v1/admin/graph/weights
```

Реальный ответ на CSV из 5 строк, где строки 3–5 некорректны
(`1,2,,2,` / `…,,,` / `…,,-1,`):

```json
{
  "filename": "jam.csv",
  "format": "csv",
  "rows_total": 5,
  "rows_applied": 2,
  "rows_skipped": 3,
  "edges_updated": 2,
  "skipped": [
    {"row": 3, "reason": "узел u='1' отсутствует в графе"},
    {"row": 4, "reason": "нужно ровно одно из полей: travel_time или multiplier"},
    {"row": 5, "reason": "multiplier должен быть числом > 0, получено '-1'"}
  ],
  "skipped_truncated": false,
  "changed": true,
  "persisted": true,
  "graph": {
    "status": "ready",
    "error": null,
    "version": 2,
    "source": "weights:jam.csv",
    "nodes": 10732,
    "edges": 27374,
    "loaded_at": "2026-11-01T19:26:15.257808Z",
    "bbox": {"min_lat": 56.1852248, "min_lon": 43.7568534, "max_lat": 56.4544954, "max_lon": 44.2411582},
    "branch_nodes_cached": 7,
    "graph_path": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
    "file_exists": true,
    "file_size_bytes": 6935396,
    "file_modified_at": "2026-11-01T19:26:15.209924Z",
    "upload_max_mb": 100.0
  },
  "elapsed_ms": 373.2
}
```

| Поле | Описание |
|---|---|
| `format` | `csv` или `json` (по расширению / первому символу файла) |
| `rows_total` | Строк данных в файле |
| `rows_applied` / `rows_skipped` | Применено / пропущено строк |
| `edges_updated` | Изменено рёбер (строка без `key` может изменить несколько) |
| `skipped` | Причины пропуска, `row` — номер строки данных с 1 (не более 50) |
| `skipped_truncated` | Причин больше 50 |
| `changed` | Граф в памяти заменён |
| `persisted` | Новый граф сохранён в `GRAPH_PATH` |
| `graph` | `GraphInfo` после операции |

Другие причины пропуска: `ребра 1→2 нет в графе`, `ребра u→v с key=5 нет в графе`,
`некорректный key='x'`, `travel_time должен быть числом > 0, получено ...`,
`строка должна быть объектом` (JSON), `у ребра нет travel_time — множитель не к чему применить`.

Ошибки:

| Код | `detail` |
|---|---|
| 409 | `Граф загружается при старте — повторите позже` |
| 413 | `Файл больше допустимых 100 МБ` |
| 415 | Файл pickle (см. ниже) |
| 422 | `CSV: нужны колонки u, v и travel_time или multiplier (key — опц.)` |
| 422 | `Некорректный JSON: ...`, `JSON: нужен массив строк или объект с массивом rows`, `Файл должен быть в кодировке UTF-8`, `Пустой файл` |
| 503 | `Граф дорог не загружен — веса обновлять не к чему` |

### `POST /admin/graph/upload`

Загрузить **новый граф целиком**. `multipart/form-data`, поле `file`. Форматы:

- **GraphML** (`.graphml`/`.xml` или содержимое начинается с `<`) — файл `ox.save_graphml`
  (читается `ox.load_graphml`) или `nx.write_graphml` (запасной вариант `nx.read_graphml`;
  числовые строковые id узлов приводятся к int);
- **JSON node-link** (`.json` или начинается с `{`) — `nx.node_link_data(G, edges="edges")`;
  ключ рёбер `edges` или `links`. Граф читается как направленный мультиграф.

**Pickle не принимается никогда** (по расширению `.pkl`, `.pickle`, `.p`, `.pck`, `.joblib`,
`.dill` или по сигнатуре `0x80`) — его распаковка выполняет произвольный код. Pickle пишет и
читает только сам сервер (`GRAPH_PATH`).

Требования проверки: граф не пуст (есть узлы и рёбра); у каждого узла числовые `x`
(долгота, −180..180) и `y` (широта, −90..90); у каждого ребра `travel_time` > 0 (секунды).
Остальные атрибуты (`length`, `name`, …) сохраняются, но не обязательны.

Минимальный node-link (фрагмент файла, выгруженного из реального графа; сокращено, числа округлены):

```json
{
  "directed": true,
  "multigraph": true,
  "graph": {"crs": "epsg:4326"},
  "nodes": [
    {"id": 1656796928, "x": 43.9790447, "y": 56.300433},
    {"id": 5519194243, "x": 43.9784136, "y": 56.3004423}
  ],
  "edges": [
    {"source": 1656796928, "target": 1999716624, "key": 0, "travel_time": 3.66, "length": 20.35}
  ]
}
```

Минимальный GraphML (атрибуты `x`, `y` у узлов и `travel_time` у рёбер):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="x" for="node" attr.name="x" attr.type="double"/>
  <key id="y" for="node" attr.name="y" attr.type="double"/>
  <key id="tt" for="edge" attr.name="travel_time" attr.type="double"/>
  <graph edgedefault="directed">
    <node id="1"><data key="x">43.9790</data><data key="y">56.3004</data></node>
    <node id="2"><data key="x">43.9784</data><data key="y">56.3005</data></node>
    <edge source="1" target="2"><data key="tt">12.5</data></edge>
    <edge source="2" target="1"><data key="tt">12.5</data></edge>
  </graph>
</graphml>
```

```powershell
curl.exe -H "Authorization: Bearer $token" -F "file=@small.json" http://localhost:8000/api/v1/admin/graph/upload
```

Ответ 200 (`GraphChangeResult`; загружен подграф из 42 узлов):

```json
{
  "action": "upload",
  "format": "node-link",
  "persisted": true,
  "graph": {
    "status": "ready",
    "error": null,
    "version": 5,
    "source": "upload:small.json",
    "nodes": 42,
    "edges": 79,
    "loaded_at": "2026-11-01T19:26:16.171847Z",
    "bbox": {"min_lat": 56.300295, "min_lon": 43.9354957, "max_lat": 56.3161019, "max_lon": 43.9834183},
    "branch_nodes_cached": 7,
    "graph_path": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
    "file_exists": true,
    "file_size_bytes": 6275,
    "file_modified_at": "2026-11-01T19:26:16.168809Z",
    "upload_max_mb": 100.0
  },
  "elapsed_ms": 27.6
}
```

`format` — `graphml` или `node-link`. **Внимание:** загруженный граф перезаписывает
`GRAPH_PATH` — прежний файл не сохраняется.

Ошибки:

| Код | `detail` |
|---|---|
| 409 | `Граф загружается при старте — повторите позже` |
| 413 | `Файл больше допустимых 100 МБ` |
| 415 | `Pickle не принимается (распаковка выполняет произвольный код): используйте GraphML или JSON node-link` |
| 415 | `Поддерживаются GraphML (.graphml) и JSON node-link (.json)` |
| 422 | `Граф должен содержать узлы и рёбра`, `Некорректный GraphML: ...`, `Некорректный JSON: ...`, `JSON node-link: нужен объект с массивом nodes` |
| 422 | Проверка не пройдена — `detail` **объект** со списком ошибок (не более 50) |

Пример 422 с ошибками проверки:

```json
{
  "detail": {
    "message": "Граф не прошёл проверку",
    "errors": [
      "Узел 2: нет числовых координат x/y",
      "Ребро (1, 2, 0): нужен travel_time > 0 (секунды)"
    ]
  }
}
```

### `POST /admin/graph/reload`

Перечитать граф из `GRAPH_PATH` (pickle, записанный сервером) без перезапуска — например,
после ручной замены файла. Тела нет.

```powershell
curl.exe -X POST -H "Authorization: Bearer $token" http://localhost:8000/api/v1/admin/graph/reload
```

```json
{
  "action": "reload",
  "format": "pickle",
  "persisted": false,
  "graph": {
    "status": "ready",
    "error": null,
    "version": 4,
    "source": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
    "nodes": 10732,
    "edges": 27374,
    "loaded_at": "2026-11-01T19:26:16.104135Z",
    "bbox": {"min_lat": 56.1852248, "min_lon": 43.7568534, "max_lat": 56.4544954, "max_lon": 44.2411582},
    "branch_nodes_cached": 7,
    "graph_path": "E:\\LIBRARIES\\Pizza-Analysis-System\\data\\nn_graph.pkl",
    "file_exists": true,
    "file_size_bytes": 6935396,
    "file_modified_at": "2026-11-01T19:26:15.717266Z",
    "upload_max_mb": 100.0
  },
  "elapsed_ms": 287.6
}
```

Ошибки: 404 `Файл графа не найден: <путь>`, 409 `Граф загружается при старте — повторите
позже`, 422 `Не удалось загрузить граф из файла: ...` (в памяти остаётся прежний граф).
Скачивание из OSM при reload не выполняется.

## 15. Граф дорог: жизненный цикл

Граф дорог Нижнего Новгорода (`networkx.MultiDiGraph` из osmnx, ~10.7 тыс. узлов и
~27.4 тыс. рёбер, вес `travel_time` в секундах) держится в памяти процесса в
`app.state.graph_registry` (`backend/app/core/graph_state.py`).

**Загрузка при старте.** При `LOAD_GRAPH_ON_STARTUP=true` lifespan запускает чтение
`GRAPH_PATH` в фоновом потоке — API отвечает сразу. Если файла нет и
`GRAPH_DOWNLOAD_IF_MISSING=true`, граф скачивается из OpenStreetMap штатным загрузчиком ML-части
(несколько минут) и сохраняется. После чтения строится BallTree по узлам (поиск ближайшего
узла за O(log n)).

**Статусы** (`GET /admin/graph/info` → `status`; `/health/ready` → `components.graph`):

| `GraphRegistry.status` | `/health/ready` graph | Маршруты (`/recommendations/driver*`) |
|---|---|---|
| `not_loaded` (`LOAD_GRAPH_ON_STARTUP=false`) | `not_configured`, `required: false`, 200 | 503, `Retry-After: 300` |
| `loading` (первая загрузка) | `loading`, 503 | 503, `Retry-After: 30` |
| `ready` | `ok`, 200 | работают |
| `failed` | `error`, 503 (если граф обязателен) | 503, `Retry-After: 300` |

Если перезагрузка не удалась, а граф уже был загружен, — статус остаётся `ready`, сервис
работает на прежнем графе, текст ошибки виден в `error`.

**Ответы 503** (реальные):

```
HTTP/1.1 503 Service Unavailable
Retry-After: 30

{"detail": "Граф дорог загружается, повторите позже"}
```

```
HTTP/1.1 503 Service Unavailable
Retry-After: 300

{"detail": "Граф дорог не загружен"}
```

```
HTTP/1.1 503 Service Unavailable
Retry-After: 300

{"detail": "Граф дорог не загружен: FileNotFoundError: Файл графа не найден: data/nn_graph.pkl"}
```

Клиенту стоит повторить запрос через `Retry-After` секунд. Эндпоинты K-Means
(`/recommendations/branches*`) граф не используют и работают всегда.

**Обновление на лету.** `POST /admin/graph/weights`, `/upload`, `/reload` подменяют граф без
перезапуска: новый снимок строится целиком, затем ссылка атомарно заменяется. Каждый запрос
маршрута берёт снимок в начале и работает с ним до конца, поэтому замена не ломает
выполняющиеся запросы; в ответе `/recommendations/driver` видно `graph_version`, на котором
посчитан маршрут. Изменения сохраняются в `GRAPH_PATH` и переживают перезапуск.

## 16. Тесты и линтер

Из корня репозитория:

```powershell
.venv\Scripts\python.exe -m ruff check backend
.venv\Scripts\python.exe -m ruff format --check backend
.venv\Scripts\python.exe -m pytest -q
```

Тесты (`backend/tests/`) не требуют PostgreSQL и реального графа: БД — SQLite in-memory
(`dependency_overrides[get_db]`), граф — маленький синтетический `nx.MultiDiGraph`,
`LOAD_GRAPH_ON_STARTUP=false`. Настройки ruff и pytest — в `pyproject.toml`
(длина строки 100).
