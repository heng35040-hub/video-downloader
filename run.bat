@echo off
rem 优先用作者本机的解释器；别人装在别处时自动回退 PATH 里的 pythonw
set "PY=pythonw.exe"
if not exist "%PY%" set "PY=pythonw.exe"
start "" "%PY%" "%~dp0main.py"
