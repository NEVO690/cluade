@echo off
rem Dedicated Xgun match server. Players join from PLAY > PLAY ONLINE > JOIN with this PC's address.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\python.exe -m net.match_server --port 47800 %*
pause
