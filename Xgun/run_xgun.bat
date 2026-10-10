@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\python.exe main.py %*
if errorlevel 1 (
  echo.
  echo Xgun closed with an error. See userdata\logs\xgun.log
  pause
)
