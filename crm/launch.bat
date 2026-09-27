@echo off
REM Specter CRM launcher (Windows). Double-click it, or run it from anywhere.
REM First run: creates .venv at the repo root, installs requirements, and offers demo data.
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" goto install
echo Setting up a Python environment in .venv ...
python -m venv .venv
if errorlevel 1 (
  echo Python 3.11 or newer is required: https://www.python.org/downloads/
  pause
  exit /b 1
)
:install
".venv\Scripts\python.exe" -m pip install -q -r crm\requirements.txt --disable-pip-version-check

if exist "crm\crm.db" goto run
set "DEMO=Y"
set /p "DEMO=No database yet. Load fictional demo data? [Y/n] "
if /i "%DEMO%"=="n" goto run
".venv\Scripts\python.exe" -m crm.seed_demo

:run
echo Specter CRM: http://localhost:8090   (Ctrl+C to stop)
if not defined CRM_NO_BROWSER start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8090"
".venv\Scripts\python.exe" -m uvicorn crm.server:app --host 127.0.0.1 --port 8090
pause
