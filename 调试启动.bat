@echo off
chcp 65001 >nul
cd /d "%~dp0"
set MOYU_DEBUG=1
echo ===== start %date% %time% =====
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python37\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python37\pythonw.exe"
if not defined PYW if exist "D:/Python/pythonw.exe" set "PYW=D:/Python/pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python38\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python38\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe"

if not defined PYW (
  echo [ERROR] pythonw.exe not found.
  pause
  exit /b 1
)

echo using: %PYW%
"%PYW%" "%~dp0main.py"
echo ---- exit code: %errorlevel% ----
if exist "data\error.log" type "data\error.log"
if exist "data\debug.log" type "data\debug.log"
pause
