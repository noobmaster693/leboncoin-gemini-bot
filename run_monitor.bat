@echo off
setlocal

title Leboncoin Gemini Bot Monitor
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Virtual environment not found.
  echo Run setup first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\activate.bat
  echo   pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist ".env" (
  echo ERROR: .env file not found.
  echo Create it first:
  echo   copy .env.example .env
  echo Then edit it with your Gemini, Gmail, and Telegram values.
  pause
  exit /b 1
)

echo Starting 24/7 Leboncoin Gemini Bot monitor...
echo Leave this window open. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" scripts\monitor.py

echo.
echo Monitor stopped.
pause
