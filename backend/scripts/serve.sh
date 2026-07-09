#!/usr/bin/env bash
# Start the backend API in the background (idempotent) and verify health.
cd "$(dirname "$0")/.."
if ! curl -s -m 2 localhost:8000/health > /dev/null 2>&1; then
  nohup uv run uvicorn app.main:app --port 8000 > ../.uvicorn.log 2>&1 &
  sleep 6
fi
curl -s localhost:8000/health
echo
curl -s localhost:8000/api/research
echo
