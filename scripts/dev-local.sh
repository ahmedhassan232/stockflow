#!/usr/bin/env bash
# Run StockFlow WITHOUT Docker (needs local PostgreSQL 17, Redis, Python 3.12+, Node 20.19+).
# Usage: scripts/dev-local.sh setup | test
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  setup)
    [ -f backend/.env ] || { echo "Create backend/.env first (see README → Run without Docker)"; exit 1; }
    python3 -m venv backend/.venv
    backend/.venv/bin/pip install -q -e "backend[dev]"
    (cd backend && set -a && . ./.env && set +a && .venv/bin/alembic upgrade head)
    (cd frontend && npm ci)
    echo "Done. Start:  (cd backend && .venv/bin/uvicorn app.main:app --reload)   and   (cd frontend && npm run dev)"
    ;;
  test)
    (cd backend && set -a && . ./.env && set +a && .venv/bin/ruff check . && .venv/bin/pytest)
    (cd frontend && npm run typecheck && npm test)
    ;;
  *) echo "Usage: $0 setup|test"; exit 2 ;;
esac
