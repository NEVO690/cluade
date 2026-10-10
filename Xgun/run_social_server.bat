@echo off
rem Shared social server for the short-video tab. Players use "Go online" with this PC's address.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\python.exe -m net.social_server --port 47801 --data server_data %*
pause
