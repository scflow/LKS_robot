#!/usr/bin/env bash
# 一键启动 Flask 后端与前端 Vite 开发服务

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLASK_PID=""
VITE_PID=""

cleanup() {
  echo ""
  echo ">> Stopping services..."
  if [[ -n "$VITE_PID" ]] && ps -p "$VITE_PID" >/dev/null 2>&1; then
    kill "$VITE_PID" || true
  fi
  if [[ -n "$FLASK_PID" ]] && ps -p "$FLASK_PID" >/dev/null 2>&1; then
    kill "$FLASK_PID" || true
  fi
}

trap cleanup INT TERM EXIT

echo ">> Starting Flask backend (python3 app.py)"
(
  cd "$ROOT_DIR"
  /usr/local/bin/python3 app.py
) &
FLASK_PID=$!

echo ">> Starting frontend (npm run dev -- --host) in frontend/"
(
  cd "$ROOT_DIR/frontend"
  npm run dev -- --host
) &
VITE_PID=$!

echo ">> Services started:"
echo "   Flask PID : $FLASK_PID (http://127.0.0.1:5001)"
echo "   Vite  PID : $VITE_PID (frontend dev server)"
echo ">> Press Ctrl+C to stop both."

wait
