#!/usr/bin/env bash
# Start the Next.js dev server in the background (idempotent) and wait for readiness.
cd "$(dirname "$0")/.."
if ! curl -s -m 2 localhost:3000 > /dev/null 2>&1; then
  nohup npm run dev > ../.next-dev.log 2>&1 &
  for i in $(seq 1 40); do
    sleep 2
    curl -s -m 2 -o /dev/null localhost:3000 && break
  done
fi
curl -s -o /dev/null -w "frontend: %{http_code}\n" localhost:3000
