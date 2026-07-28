#!/usr/bin/env bash
# FlowHub - Start local development stack
#
# Creates an isolated SQLite runtime under .local/dev, starts FastAPI with
# reload, and starts the Vite development server. Local credentials and
# generated configuration remain ignored by Git.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing .venv. Create a Python 3.12 virtual environment and install requirements first." >&2
  exit 1
fi

"${PYTHON}" "${ROOT}/scripts/dev/bootstrap_local.py"

set -a
# shellcheck disable=SC1091
source "${ROOT}/.local/dev/backend.env"
set +a

cleanup() {
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "${ROOT}"
"${PYTHON}" -m uvicorn app.flowhub.app:app --reload --reload-dir app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

cd "${ROOT}/frontend"
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

echo "FlowHub frontend: http://127.0.0.1:5173"
wait "${BACKEND_PID}" "${FRONTEND_PID}"
