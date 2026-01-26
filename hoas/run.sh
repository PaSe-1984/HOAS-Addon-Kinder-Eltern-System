#!/usr/bin/env bash
echo "[HOAS] Starting..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
