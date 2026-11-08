#!/bin/sh
set -eu

url="${SMOKE_URL:-http://127.0.0.1:8000/api/v1/health/ready}"
attempts="${SMOKE_ATTEMPTS:-30}"
delay="${SMOKE_DELAY_SECONDS:-2}"

attempt=1
while [ "$attempt" -le "$attempts" ]; do
    if response="$(curl --fail --silent --show-error --max-time 5 "$url")"; then
        printf '%s\n' "$response"
        printf 'Smoke test passed: %s\n' "$url"
        exit 0
    fi

    printf 'Smoke test attempt %s/%s failed; retrying in %ss...\n' \
        "$attempt" "$attempts" "$delay" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
done

printf 'Smoke test failed after %s attempts: %s\n' "$attempts" "$url" >&2
exit 1

