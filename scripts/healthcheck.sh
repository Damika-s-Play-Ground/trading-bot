#!/usr/bin/env bash
set -euo pipefail

APP_URL="${1:-http://127.0.0.1:8008/healthz}"
if ! curl -fsS --max-time 10 "$APP_URL" >/dev/null; then
  echo "healthcheck failed for $APP_URL" >&2
  exit 1
fi
