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

Проверки перед коммитом:

```powershell
ruff check backend
ruff format --check backend
pytest -q
```
