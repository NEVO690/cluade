@echo off
REM Creates a local virtual environment and installs Xgun's dependencies.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :error
echo.
echo Xgun is installed. Start the game with run_xgun.bat
pause
exit /b 0
:error
echo Installation failed. Make sure 64-bit Python 3.10-3.13 is installed and on PATH.
pause
exit /b 1
