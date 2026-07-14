#!/usr/bin/env bash

set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_PORT=8000
FRONTEND_PORT=5173
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  status=$?
  trap - EXIT INT TERM

  echo
  echo "Stopping RNABag frontend and backend..."

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]]; then
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  echo "RNABag frontend and backend stopped."
  exit "$status"
}

trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup EXIT

cd "$PROJECT_ROOT"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

echo "Starting RNABag backend:  http://127.0.0.1:${BACKEND_PORT}"
RNABAG_DEVICE="${RNABAG_DEVICE:-cpu}" \
RNABAG_BATCH_SIZE="${RNABAG_BATCH_SIZE:-1}" \
  "$PYTHON_BIN" -m uvicorn backend.app.main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Starting RNABag frontend: http://127.0.0.1:${FRONTEND_PORT}/"
"$PYTHON_BIN" -m http.server "$FRONTEND_PORT" \
  --bind 127.0.0.1 \
  --directory "$PROJECT_ROOT" &
FRONTEND_PID=$!

echo "Press Ctrl+C to stop both processes."

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

echo "A child process exited unexpectedly; stopping the remaining process." >&2
exit 1
