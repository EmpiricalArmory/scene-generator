@echo off
title Empirical Armory - Scene Generator setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install.ps1" %*
echo.
echo You can close this window.
pause >nul
