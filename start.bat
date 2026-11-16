@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python37\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python37\pythonw.exe"
if not defined PYW if exist "D:/Python/pythonw.exe" set "PYW=D:/Python/pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python38\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python38\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"

if defined PYW goto run
where pyw >nul 2>nul
if not errorlevel 1 goto launcher
echo [ERROR] pythonw.exe not found. Install Python 3.7+ or edit this file.
pause
exit /b 1

:run
start "" "%PYW%" "%~dp0main.py"
exit /b 0

:launcher
start "" pyw -3 "%~dp0main.py"
exit /b 0
