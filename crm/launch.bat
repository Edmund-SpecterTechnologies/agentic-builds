@echo off
REM CRM launcher (Windows). Run from anywhere; serves http://localhost:8090
cd /d "%~dp0.."
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
pip install -r crm\requirements.txt -q --disable-pip-version-check 2>nul
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8090"
python -m uvicorn crm.server:app --host 127.0.0.1 --port 8090
pause
