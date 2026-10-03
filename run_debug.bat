@echo off
rem Debug launcher: keeps a console so errors are visible.
chcp 65001 >nul
set "PY=python.exe"
if not exist "%PY%" set "PY=python.exe"
"%PY%" "%~dp0main.py"
echo.
pause
