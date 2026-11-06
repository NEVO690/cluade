@echo off
chcp 65001 >nul
title IL Brawl
cd /d "%~dp0"

rem --- find Python 3 -------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

rem --- install pygame on first run ----------------------------------------
%PY% -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo Installing game requirements ^(first run only^)...
    %PY% -m pip install --user -r requirements.txt
    if errorlevel 1 (
        echo Could not install pygame. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

rem --- start the game -------------------------------------------------------
%PY% main.py
if errorlevel 1 (
    echo.
    echo The game closed with an error. Details: saves\logs\crash.log
    pause
)
