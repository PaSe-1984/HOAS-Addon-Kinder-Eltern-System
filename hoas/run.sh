#!/usr/bin/env bash
echo "Starting HOAS..."
uvicorn app.main:app --host 0.0.0.0 --port 8080