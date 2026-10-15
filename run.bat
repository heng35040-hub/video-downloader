@echo off
rem 静默启动（无控制台窗口）。优先 py 启动器，其次 PATH 里的 pythonw。
where pyw >nul 2>nul && (start "" pyw "%~dp0main.py" & exit /b)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0main.py" & exit /b)
echo [错误] 未找到 Python。请安装 Python 3.10+ 并勾选 "Add python.exe to PATH"。
pause
