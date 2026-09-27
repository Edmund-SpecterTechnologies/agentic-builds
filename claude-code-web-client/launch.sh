#!/usr/bin/env bash
# Claude Code Web Client launcher (macOS/Linux)
# Optional: export CLAUDE_WORKSPACE=/path/to/project  (defaults to this repo's root)

cd "$(dirname "$0")" || exit 1
[ -f ../.venv/bin/activate ] && source ../.venv/bin/activate
pip install -r requirements.txt -q --disable-pip-version-check >/dev/null 2>&1

(
  sleep 3
  if command -v open >/dev/null 2>&1; then open http://localhost:8765
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8765
  fi
) &

python -m uvicorn server:app --host 127.0.0.1 --port 8765
