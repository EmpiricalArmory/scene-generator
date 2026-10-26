@echo off
title Empirical Armory - Scene Generator
cd /d "%~dp0"
if not exist "ComfyUI_windows_portable\python_embeded\python.exe" (
  echo The generator is not installed yet: run Install.bat first.
  pause
  exit /b 1
)
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0setup\open-when-ready.ps1"
cd /d "%~dp0ComfyUI_windows_portable"
:run
echo Starting the generator. Leave this window open while you use it; it opens in your browser.
echo.
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --disable-auto-launch --listen 127.0.0.1 --port 8188 --preview-method auto
if %errorlevel%==42 (
  echo.
  echo Restarting...
  goto run
)
echo.
echo The generator has stopped. You can close this window.
pause >nul
