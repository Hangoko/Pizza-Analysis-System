# Pizza-Analysis-System
Сбор метрик заказов, генерация отчетов, рекомендации по маршрутам, оптимизация сети филиалов.


## Запуск бэкенда локально

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

Проверки перед коммитом:

```powershell
ruff check backend
ruff format --check backend
pytest -q
```
