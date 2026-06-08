#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/app"
PORT="${PROFILE_MANAGER_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"
OUT="$APP/manager.out.log"
ERR="$APP/manager.err.log"
PID_FILE="$APP/manager.pid"

if command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "python3 was not found. Install Python 3 first." >&2
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

: > "$OUT"
: > "$ERR"

PROFILE_MANAGER_PORT="$PORT" "$PYTHON" "$APP/server.py" > "$OUT" 2> "$ERR" &
echo $! > "$PID_FILE"

for _ in $(seq 1 30); do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    open "$URL"
    exit 0
  fi
  sleep 0.2
done

cat "$ERR" >&2 || true
echo "Profile Manager did not start. Check $ERR" >&2
exit 1
