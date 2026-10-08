@echo off
REM SUBWAY SURFER CITY - one-time setup (creates .venv and installs the packages)
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Could not create a virtual environment.
  echo Install Python 3.9+ from https://www.python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip uninstall -y pygame >nul 2>nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Installing packages failed - see the messages above.
  pause
  exit /b 1
)
echo.
echo Done! Start the game with run_game.bat
pause
