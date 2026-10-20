#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npm run build
uv run pytest -q
uv run python scripts/evaluate.py

