@echo off
rem BONK! - install dependencies into a local virtual environment (Windows)
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :error
echo.
echo Installed. Start the game with run_game.bat
goto :eof
:error
echo Installation failed. Make sure Python 3.11+ (64-bit) is installed and on PATH.
