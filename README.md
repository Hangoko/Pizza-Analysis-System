# NewFastPizza — Pizza-Analysis-System

Интеллектуальная система сбора метрик заказов, генерации аналитической отчетности, рекомендаций по маршрутизации курьеров и оптимизации сети филиалов на базе машинного обучения.

---

## Архитектура системы

Проект организован по принципу монорепозитория:

```
Pizza-Analysis-System/
├── backend/                  # REST API на FastAPI (Python 3.12)
│   ├── app/
│   │   ├── api/v1/           # Роуты: auth, stats, reports, recommendations, admin
│   │   ├── core/             # Конфигурация Pydantic-Settings и безопасность (JWT)
│   │   ├── db/               # SQLAlchemy 2.0 модели, миграции Alembic
│   │   ├── ml/               # Алгоритмы K-Means, маршрутизация Дейкстры, генератор
│   │   ├── repositories/     # Слой абстракции данных (Repository pattern)
│   │   └── services/         # Бизнес-логика, быстрая маршрутизация и адаптеры карт
│   ├── tests/                # Модульные и интеграционные тесты Pytest (181 тест)
│   ├── requirements.txt      # Зафиксированные production-зависимости
│   ├── requirements-dev.txt  # Зависимости для тестирования и разработки (pytest, ruff)
│   └── README.md             # Полная спецификация 31 эндпоинта Backend API
├── frontend/                 # Клиентское SPA-приложение (Vue 3 + TypeScript + Vite)
│   ├── src/
│   │   ├── api/              # Типизированный клиент API с Bearer-авторизацией
│   │   ├── layouts/          # Корпоративный AppLayout с фильтрацией навигации по ролям
│   │   ├── router/           # Vue Router с guards проверки прав доступа (RBAC)
│   │   ├── stores/           # Pinia-хранилище аутентификации и сессии
│   │   ├── types/            # TypeScript-интерфейсы моделей и DTO
│   │   └── views/            # Экраны: Dashboard, DriverMap, BranchesMap, Reports, Admin
│   ├── package.json          # Зависимости интерфейса (Chart.js, Tailwind CSS, Lucide)
│   └── vite.config.ts        # Конфигурация Vite с реверс-прокси к API
├── data/                     # Датасеты и кэш графа дорог Нижнего Новгорода
└── docs/                     # Архитектурная документация и ER-диаграммы БД
```

---

## Требования к окружению

- **Python 3.12** (версия строго 3.12 для совместимости с зафиксированными сборками pandas / scikit-learn / osmnx).
- **Node.js 18+** и менеджер пакетов `npm`.
- **PostgreSQL 16** (локально или через Docker).

---

## Быстрый старт

### 1. Запуск базы данных (PostgreSQL)

Для локальной разработки поднимите контейнер PostgreSQL:

```bash
docker run -d --name pizza-pg \
  -e POSTGRES_USER=pizza \
  -e POSTGRES_PASSWORD=pizza \
  -e POSTGRES_DB=pizza \
  -p 5432:5432 postgres:16-alpine
```

### 2. Запуск Backend API

Все команды выполняются из корня репозитория:

```bash
# Создание и активация виртуального окружения
py -3.12 -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate

# Установка зависимостей (ML, FastAPI, тесты, линтер)
python -m pip install -r backend/requirements-dev.txt

# Применение миграций Alembic
alembic -c backend/alembic.ini upgrade head

# Наполнение БД демо-данными (7 филиалов, 20 водителей, синтетические заказы)
python -m backend.app.scripts.seed

# Запуск API-сервера в режиме разработки с автоперезагрузкой
uvicorn backend.app.main:app --reload --port 8000
```

После запуска бэкенда доступны:
- **Интерактивная документация Swagger UI:** http://localhost:8000/docs
- **ReDoc спецификация:** http://localhost:8000/redoc
- **OpenAPI JSON схема:** http://localhost:8000/openapi.json
- **Health Check готовности системы:** http://localhost:8000/api/v1/health/ready

### 3. Запуск Frontend SPA

Перейдите в директорию `frontend/`:

```bash
cd frontend

# Установка зависимостей интерфейса
npm install

# Запуск сервера разработки Vite
npm run dev
```

Приложение доступно по адресу: **http://localhost:5173**.  
Запросы к `/api/*` автоматически проксируются на бэкенд `http://localhost:8000`.

---

## Тестирование и проверка качества кода

### Тесты бэкенда (Pytest)

Полный набор модульных и интеграционных тестов (181 тест) на базе SQLite in-memory:

```bash
# Запуск полного тестового набора
pytest -v

# Запуск целевых тестов ML-пайплайна (генератор, K-Means, Дейкстра)
pytest -v backend/tests/test_ml_pipeline.py

# Проверка линтером Ruff
ruff check backend/
ruff format --check backend/
```

### Проверка фронтенда (TypeScript & Vite)

```bash
cd frontend

# Проверка строгой типизации TypeScript
npm run typecheck

# Сборка продакшен-бандла
npm run build
```

---

## Ролевая модель доступа (RBAC)

Аутентификация построена на JWT-токенах (HS256) в соответствии с OAuth2 Password Flow.

| Раздел интерфейса | admin | manager | executive | driver |
|---|:---:|:---:|:---:|:---:|
| **Аналитика и KPI** (`/dashboard`) | ✓ | ✓ | ✓ | — |
| **Рекомендации курьеру** (`/map/driver`) | ✓ | ✓ | — | ✓ |
| **Зоны спроса K-Means** (`/map/branches`) | ✓ | ✓ | ✓ | — |
| **Отчеты и экспорт CSV** (`/reports`) | ✓ | ✓ (свои + системные) | ✓ (чтение/экспорт) | — |
| **Управление пользователями** (`/admin/users`) | ✓ | — | — | — |
| **Граф дорог и пробки** (`/admin/graph`) | ✓ | — | — | — |

На экране входа (`/login`) предусмотрены кнопки быстрого демо-переключения между ролями для оперативного тестирования интерфейса.

---

## Дополнительная документация

- [backend/README.md](backend/README.md) — исчерпывающее описание всех 31 эндпоинтов REST API v1, формат параметров, схемы ответов и коды ошибок.
- [docs/er-diagram.md](docs/er-diagram.md) — схема сущностей и связей базы данных (ER-диаграмма).
