#!/usr/bin/env bash
# Local dev: AI-assist pathologist review (same study as production, SQLite API).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BACKEND_PID=""
CONFIG_BACKUP=""
cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${CONFIG_BACKUP}" && -f "${CONFIG_BACKUP}" ]]; then
    mv -f "${CONFIG_BACKUP}" config.json
  fi
}
trap cleanup EXIT

API_PORT="${AI_ASSIST_API_PORT:-8781}"
PORT="${PORT:-8772}"

if [[ -f config.json && ! -L config.json ]]; then
  CONFIG_BACKUP="$(mktemp)"
  cp config.json "${CONFIG_BACKUP}"
fi
cp config.local.json config.json

if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "Starting local API on http://127.0.0.1:${API_PORT} (SQLite, not production) …"
  (
    cd backend
    if [[ ! -d .venv ]]; then
      python3 -m venv .venv
      .venv/bin/pip install -q -r requirements.txt
    fi
    REVIEW_DB_BACKEND=sqlite SQLITE_PATH=data/ai_assist_local.db \
      STUDY_ID=rosai-ai-assist-correct-v1 \
      ASSIGNMENTS_URL="file://${ROOT}/assignments.json" \
      CORS_ORIGINS="http://127.0.0.1:${PORT},http://localhost:${PORT}" \
      .venv/bin/uvicorn main:app --host 127.0.0.1 --port "${API_PORT}"
  ) &
  BACKEND_PID=$!
  for _ in $(seq 1 30); do
    curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "WARNING: Local API failed to start on port ${API_PORT}." >&2
  fi
fi

echo ""
echo "AI assist review (local): http://127.0.0.1:${PORT}/?reviewer=reviewer_1"
echo "Local API (SQLite):       http://127.0.0.1:${API_PORT}"
echo "Production site:          https://jaumelab.github.io/rosai-pathologist-review-ai-assist/"
echo "Press Ctrl+C to stop."
python3 -m http.server "${PORT}"
