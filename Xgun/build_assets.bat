@echo off
REM Regenerates every 3D asset (.blend sources, .glb models, Cycles thumbnails) with Blender.
REM Usage: build_assets.bat [categories...]   e.g. build_assets.bat characters weapons
cd /d "%~dp0"
set BLENDER=blender
if exist "%ProgramFiles%\Blender Foundation" (
  for /d %%D in ("%ProgramFiles%\Blender Foundation\Blender*") do set BLENDER="%%D\blender.exe"
)
%BLENDER% --background --factory-startup --python tools\blender_generation\build_all.py -- %*
.venv\Scripts\python.exe tools\asset_validation\validate_assets.py
pause
