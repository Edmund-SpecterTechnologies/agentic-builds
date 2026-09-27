#!/usr/bin/env sh
# Specter CRM launcher (macOS/Linux):  sh crm/launch.sh
# First run: creates .venv at the repo root, installs requirements, and offers demo data.
set -e
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "Setting up a Python environment in .venv ..."
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r crm/requirements.txt --disable-pip-version-check

if [ ! -f crm/crm.db ]; then
  printf "No database yet. Load fictional demo data? [Y/n] "
  read -r DEMO || DEMO=Y
  case "$DEMO" in n|N) ;; *) .venv/bin/python -m crm.seed_demo ;; esac
fi

echo "Specter CRM: http://localhost:8090   (Ctrl+C to stop)"
if [ -z "$CRM_NO_BROWSER" ]; then
  ( sleep 2
    if command -v open >/dev/null 2>&1; then open http://localhost:8090
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8090
    fi ) &
fi
exec .venv/bin/python -m uvicorn crm.server:app --host 127.0.0.1 --port 8090
