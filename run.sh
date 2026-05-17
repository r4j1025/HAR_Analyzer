#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  HAR Tree Analyzer — start backend + frontend (each in own venv)
# ─────────────────────────────────────────────────────────────────
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[har]${NC} $*"; }
warn() { echo -e "${YELLOW}[har]${NC} $*"; }
info() { echo -e "${CYAN}[har]${NC} $*"; }

# ── create + populate backend venv ───────────────────────────────
BACKEND_VENV="$ROOT/backend/.venv"
if [ ! -d "$BACKEND_VENV" ]; then
  log "Creating backend venv..."
  python3 -m venv "$BACKEND_VENV"
fi
log "Installing backend deps..."
"$BACKEND_VENV/bin/pip" install -q --upgrade pip
"$BACKEND_VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"

# ── create + populate frontend venv ──────────────────────────────
FRONTEND_VENV="$ROOT/frontend/.venv"
if [ ! -d "$FRONTEND_VENV" ]; then
  log "Creating frontend venv..."
  python3 -m venv "$FRONTEND_VENV"
fi
log "Installing frontend deps..."
"$FRONTEND_VENV/bin/pip" install -q --upgrade pip
"$FRONTEND_VENV/bin/pip" install -q -r "$ROOT/frontend/requirements.txt"

# ── copy .streamlit config so streamlit finds it ─────────────────
mkdir -p "$ROOT/frontend/.streamlit"
cp "$ROOT/.streamlit/config.toml" "$ROOT/frontend/.streamlit/config.toml"

# ── start backend ─────────────────────────────────────────────────
log "Starting FastAPI backend on http://localhost:8000 ..."
cd "$ROOT/backend"
"$BACKEND_VENV/bin/uvicorn" main:app \
  --host 0.0.0.0 --port 8000 --reload \
  --log-level warning &
BACKEND_PID=$!

# wait until backend is ready (max 10 s)
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    log "Backend ready."; break
  fi
  sleep 0.5
done

# ── start frontend ────────────────────────────────────────────────
log "Starting Streamlit frontend on http://localhost:8501 ..."
cd "$ROOT/frontend"
"$FRONTEND_VENV/bin/streamlit" run Home.py \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false &
FRONTEND_PID=$!

echo ""
info "  Swagger API docs  →  http://localhost:8000/docs"
info "  Streamlit UI      →  http://localhost:8501"
echo ""
log "Press Ctrl+C to stop both services."

cleanup() {
  warn "Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null
  warn "Stopped."
}
trap cleanup INT TERM
wait "$BACKEND_PID" "$FRONTEND_PID"
