#!/usr/bin/env bash
# Start both backend (uvicorn) and frontend (Next.js dev server) in parallel.
# Ctrl+C kills both.
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo ""; echo "🛑 Shutting down..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  echo "done."
}
trap cleanup EXIT INT TERM

# -- Backend --
echo "🚀 Starting backend on :8000 ..."
cd "$ROOT/backend"
nohup uv run uvicorn app.main:app --port 8000 > "$ROOT/.uvicorn.log" 2>&1 &
BACKEND_PID=$!

# -- Frontend --
echo "🚀 Starting frontend on :3000 ..."
cd "$ROOT/frontend"
nohup npm run dev > "$ROOT/.next-dev.log" 2>&1 &
FRONTEND_PID=$!

# -- Wait for both --
cd "$ROOT"

echo "⏳ Waiting for backend  (http://localhost:8000/health) ..."
for i in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null http://localhost:8000/health 2>/dev/null; then
    echo "   ✅ Backend ready"
    break
  fi
  if [ "$i" -eq 30 ]; then echo "   ⚠️  Backend not ready after 30s — check .uvicorn.log"; fi
  sleep 2
done

echo "⏳ Waiting for frontend (http://localhost:3000) ..."
for i in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null http://localhost:3000 2>/dev/null; then
    echo "   ✅ Frontend ready"
    break
  fi
  if [ "$i" -eq 30 ]; then echo "   ⚠️  Frontend not ready after 30s — check .next-dev.log"; fi
  sleep 2
done

echo ""
echo "═══════════════════════════════════════════"
echo "  Backend  → http://localhost:8000/docs"
echo "  Frontend → http://localhost:3000"
echo "  Logs: tail -f .uvicorn.log / .next-dev.log"
echo "  Stop:  Ctrl+C"
echo "═══════════════════════════════════════════"

wait