@echo off
REM Claude Code Web Client launcher (Windows)
REM Optional: set CLAUDE_WORKSPACE to the project folder Claude should work in.
REM Defaults to this repo's root.

cd /d "%~dp0"

if exist "..\.venv\Scripts\activate.bat" call "..\.venv\Scripts\activate.bat"
pip install -r requirements.txt -q --disable-pip-version-check 2>nul

start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8765"
python -m uvicorn server:app --host 127.0.0.1 --port 8765
pause
