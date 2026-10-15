@echo off
rem Debug launcher: keeps a console so errors are visible.
chcp 65001 >nul
set "PY=python.exe"
where py >nul 2>nul && set "PY=py.exe"
"%PY%" "%~dp0main.py"
echo.
pause
