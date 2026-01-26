#!/usr/bin/env bash
set -e
export PATH="/opt/venv/bin:$PATH"
echo "[HOAS] Starting..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
