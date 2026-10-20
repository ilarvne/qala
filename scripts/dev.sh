#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
if [ ! -d node_modules ]; then npm ci; fi
uv sync --frozen
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
npm run dev

