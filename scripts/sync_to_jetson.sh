#!/usr/bin/env bash
# Push the repo from a laptop to the Jetson.
# Owner: Daniel
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${JETSON_HOST:-jetson}:${JETSON_DIR:-~/magic-box}/"
echo "Syncing to ${TARGET}"

rsync -az --delete --exclude .venv --exclude .git --exclude recordings --exclude .env --exclude .superpowers --exclude /.claude/worktrees \
  --exclude config.local.yaml --exclude __pycache__ --exclude .pytest_cache \
  --exclude .ruff_cache ./ "${TARGET}"
