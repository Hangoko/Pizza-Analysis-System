FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY --chown=app:app backend /app/backend
COPY --chown=app:app pyproject.toml README.md /app/
COPY --chown=app:app backend/docker/entrypoint.sh /usr/local/bin/pizza-entrypoint

RUN chmod 0755 /usr/local/bin/pizza-entrypoint \
    && mkdir -p /app/data \
    && chown app:app /app/data

USER app

EXPOSE 8000

ENTRYPOINT ["pizza-entrypoint"]
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

