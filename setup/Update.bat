@echo off
title Empirical Armory - Scene Generator update
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install.ps1" -UpdateApp -NoStart %*
echo.
echo Updated. Close the generator's window and run Start.bat again.
pause >nul
