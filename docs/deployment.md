# CI/CD и тестовый VPS

## CI для Pull Request

Workflow `.github/workflows/ci.yml` запускается для каждого Pull Request в `main` и выполняет
на Python 3.12:

```text
ruff check backend
ruff format --check backend
pytest -q
```

Для защиты `main` добавьте в GitHub branch protection обязательную проверку
`Ruff and pytest (Python 3.12)`.

## Подготовка Ubuntu 22.04

На VPS должны быть установлены Git, Docker Engine с Compose plugin и `curl`. Пользователь
деплоя должен входить в группу `docker` и иметь право записи в каталог деплоя.

Один раз создайте конфигурацию приложения:

```bash
sudo mkdir -p /opt/pizza-analysis
sudo chown "$USER":"$USER" /opt/pizza-analysis
git clone https://github.com/Hangoko/Pizza-Analysis-System.git /opt/pizza-analysis
cd /opt/pizza-analysis
cp .env.example .env
chmod 600 .env
nano .env
```

Обязательно замените `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` и `FIRST_ADMIN_PASSWORD`.
По умолчанию backend слушает только `127.0.0.1:8000`, а frontend nginx опубликован на
`0.0.0.0:8080` и проксирует `/api/` в backend. Внешний HTTPS следует завершать на nginx или
другом reverse proxy перед frontend. Адреса меняются через `BACKEND_BIND_ADDRESS`,
`BACKEND_PORT`, `FRONTEND_BIND_ADDRESS` и `FRONTEND_PORT`.

## GitHub Environment `test`

Создайте Environment `test` и добавьте secrets:

- `VPS_HOST` — IP или DNS-имя VPS;
- `VPS_USER` — непривилегированный пользователь деплоя;
- `VPS_PATH` — абсолютный путь, например `/opt/pizza-analysis`;
- `VPS_SSH_KEY` — приватный ключ Ed25519;
- `VPS_KNOWN_HOSTS` — строка `known_hosts`, полученная доверенным способом.

Если SSH работает не на порту 22, добавьте environment variable `VPS_PORT`.

После push в `main` workflow `.github/workflows/deploy-test.yml` повторно выполняет quality
gates, подключается к VPS, делает только fast-forward обновление, пересобирает Compose stack и
запускает `scripts/smoke-test.sh` против `/api/v1/health/ready`.

## Ручная проверка

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env up --detach --build
sh scripts/smoke-test.sh
docker compose --env-file .env logs --tail=100 api
```

Данные PostgreSQL и backend-граф сохраняются в именованных volumes `postgres_data` и
`graph_data`.
Команда `docker compose down` не удаляет их; не используйте `down --volumes` на VPS без
явного намерения удалить данные.

