@echo off
REM One-time setup for CivicPulse on a new machine (or after a fresh clone).
REM Needs Python 3.12+ and Node.js 20+ installed and on PATH.
setlocal
cd /d "%~dp0"

echo === Backend: Python virtual environment ===
cd backend
if not exist venv\Scripts\python.exe (
    py -3 -m venv venv 2>nul || python -m venv venv
    if errorlevel 1 ( echo Could not create venv - is Python installed? & pause & exit /b 1 )
)
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 ( echo pip install failed & pause & exit /b 1 )

if not exist .env (
    copy .env.example .env >nul
    echo Created backend\.env from .env.example - add your GEMINI_API_KEY to it.
)

echo === Backend: database + demo users ===
venv\Scripts\python.exe seed.py
cd ..

echo === Frontend: npm packages ===
cd frontend
call npm install
if errorlevel 1 ( echo npm install failed - is Node.js installed? & pause & exit /b 1 )
cd ..

echo.
echo Setup complete. Run start.bat to launch the app.
pause
