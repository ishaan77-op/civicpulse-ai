@echo off
REM Starts the Flask backend (port 5001) and Vite frontend (port 5173) in
REM their own windows, then opens the app in the browser.
setlocal
cd /d "%~dp0"

if not exist backend\venv\Scripts\python.exe ( echo Run setup.bat first. & pause & exit /b 1 )
if not exist frontend\node_modules ( echo Run setup.bat first. & pause & exit /b 1 )

start "CivicPulse backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\python.exe app.py"
start "CivicPulse frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

REM Vite serves https when frontend\.cert exists, plain http otherwise.
set URL=http://localhost:5173
if exist frontend\.cert\dev-cert.pem set URL=https://localhost:5173
timeout /t 5 /nobreak >nul
start "" %URL%
