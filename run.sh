#!/usr/bin/env bash
# Dev runner without Docker: backend (uvicorn) + frontend (vite).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "→ created .env from .env.example — add your TESTNET API keys, then re-run."
  exit 1
fi

# ── backend ──────────────────────────────────────────────────────────────────
if [[ ! -d backend/.venv ]]; then
  echo "→ creating Python venv + installing backend deps…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --prefer-binary -q -r backend/requirements.txt
fi
echo "→ starting backend on http://127.0.0.1:8000 (docs at /docs)"
(cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000) &
BACK_PID=$!

# ── frontend ─────────────────────────────────────────────────────────────────
FRONT_PID=""
if [[ -d frontend/node_modules ]]; then
  echo "→ starting dashboard on http://127.0.0.1:5173"
  # npx runs the vite binary directly — `npm run` is disabled by .npmrc
  # (ignore-scripts) as part of the supply-chain hardening.
  (cd frontend && npx vite) &
  FRONT_PID=$!
else
  cat <<'EOF'
──────────────────────────────────────────────────────────────────────────────
⚠ frontend/node_modules missing — dashboard NOT started.

  npm install is BLOCKED on this machine (supply-chain wiper incident,
  2026-08-06 — see ~/purocoach-incident-2026-08-06.md). Install the frontend
  only after this host is rebuilt, or on a clean machine / disposable VM:

      cd frontend && npm install     # .npmrc pins pre-incident versions
                                     # and disables lifecycle scripts

  The backend API is fully usable meanwhile: http://127.0.0.1:8000/docs
──────────────────────────────────────────────────────────────────────────────
EOF
fi

trap 'echo; echo "→ shutting down…"; kill $BACK_PID $FRONT_PID 2>/dev/null || true' INT TERM
wait
