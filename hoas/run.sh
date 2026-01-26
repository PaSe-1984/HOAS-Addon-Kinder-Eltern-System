#!/usr/bin/env bash
set -e
echo "[HOAS] Starting..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
