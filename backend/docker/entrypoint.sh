#!/bin/sh
set -eu

python -m alembic -c backend/alembic.ini upgrade head

if [ "${RUN_SEED:-true}" = "true" ]; then
    python -m backend.app.scripts.seed
fi

exec "$@"

