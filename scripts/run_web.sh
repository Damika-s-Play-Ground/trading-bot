#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

mkdir -p "$REPO_ROOT/logs"
exec "$REPO_ROOT/venv/bin/python3.13" app.py
