#!/usr/bin/env bash
# dev.sh — start or restart the Runbook dev environment
#
# Usage:
#   ./dev.sh          start (or restart) both backend and frontend
#   ./dev.sh stop     stop both services
#   ./dev.sh status   show running services
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
LOG_DIR="$SCRIPT_DIR/.logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
PID_FILE="$LOG_DIR/pids"

BACKEND_PORT=8001
FRONTEND_PORT=3000

# ── helpers ──────────────────────────────────────────────────────────────────

red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[0;34m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

pid_on_port() {
  # Use ss (reliable in WSL2); fall back to lsof
  ss -tlnp "sport = :$1" 2>/dev/null \
    | grep -oP 'pid=\K[0-9]+' \
    || lsof -ti "tcp:$1" 2>/dev/null \
    || true
}

port_in_use() {
  ss -tlnp "sport = :$1" 2>/dev/null | grep -q "LISTEN"
}

kill_port() {
  local port=$1 pids
  pids=$(pid_on_port "$port")
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    # Wait until the port is actually free
    for ((i=0; i<20; i++)); do
      sleep 0.3
      port_in_use "$port" || break
    done
  fi
}

wait_for_port() {
  local port=$1 label=$2 retries=40
  printf "  Waiting for %s on port %s " "$label" "$port"
  for ((i=0; i<retries; i++)); do
    if port_in_use "$port"; then
      printf ' ✓\n'
      return 0
    fi
    printf '.'
    sleep 0.5
  done
  printf ' timeout\n'
  return 1
}

# ── stop ─────────────────────────────────────────────────────────────────────

do_stop() {
  blue "Stopping services..."
  kill_port $BACKEND_PORT
  kill_port $FRONTEND_PORT
  # Also kill any saved pids
  if [[ -f "$PID_FILE" ]]; then
    while read -r pid; do
      kill "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
  green "Stopped."
}

# ── status ────────────────────────────────────────────────────────────────────

do_status() {
  bold "Runbook service status"
  if port_in_use $BACKEND_PORT; then
    green "  Backend  running  →  http://localhost:$BACKEND_PORT"
  else
    red   "  Backend  stopped"
  fi
  if port_in_use $FRONTEND_PORT; then
    green "  Frontend running  →  http://localhost:$FRONTEND_PORT"
  else
    red   "  Frontend stopped"
  fi
}

# ── start ─────────────────────────────────────────────────────────────────────

do_start() {
  mkdir -p "$LOG_DIR"

  # ── Backend ──
  blue "Starting backend..."
  kill_port $BACKEND_PORT

  # Always sync backend deps (fast no-op when nothing changed)
  echo "  Syncing backend dependencies..."
  (cd "$BACKEND_DIR" && uv pip install -r requirements.txt --quiet)

  (cd "$BACKEND_DIR" && \
    nohup uv run uvicorn app.main:app \
      --host 0.0.0.0 --port $BACKEND_PORT \
      --reload --reload-dir app \
    > "$BACKEND_LOG" 2>&1 &
    echo $! >> "$PID_FILE"
  )

  # ── Frontend ──
  blue "Starting frontend..."
  kill_port $FRONTEND_PORT
  # Clear Next.js build cache (avoids stale Turbopack artefacts and lock files)
  rm -rf "$FRONTEND_DIR/.next"

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "  Installing frontend dependencies (npm install)..."
    (cd "$FRONTEND_DIR" && npm install --silent)
  fi

  (cd "$FRONTEND_DIR" && \
    nohup npm run dev \
    > "$FRONTEND_LOG" 2>&1 &
    echo $! >> "$PID_FILE"
  )

  # ── Wait & confirm ──
  wait_for_port $BACKEND_PORT "backend" || {
    red "Backend failed to start. Logs:"
    tail -20 "$BACKEND_LOG"
    exit 1
  }
  wait_for_port $FRONTEND_PORT "frontend" || {
    red "Frontend failed to start. Logs:"
    tail -20 "$FRONTEND_LOG"
    exit 1
  }

  echo ""
  green "✓ Runbook is running"
  echo "  Frontend  →  http://localhost:$FRONTEND_PORT"
  echo "  Backend   →  http://localhost:$BACKEND_PORT"
  echo ""
  echo "  Logs: tail -f $LOG_DIR/backend.log"
  echo "        tail -f $LOG_DIR/frontend.log"
}

# ── main ──────────────────────────────────────────────────────────────────────

case "${1:-start}" in
  stop)   do_stop   ;;
  status) do_status ;;
  start)  do_start  ;;
  restart)
    do_stop
    do_start
    ;;
  *)
    red "Unknown command: $1"
    echo "Usage: $0 [start|stop|restart|status]"
    exit 1
    ;;
esac
