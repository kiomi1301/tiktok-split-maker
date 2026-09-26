@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :python_error

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

if not exist "vendor\ffmpeg\bin\ffmpeg.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_ffmpeg.ps1"
  if errorlevel 1 goto :error
)

python main.py
exit /b %errorlevel%

:python_error
echo Python was not found in PATH.
pause
exit /b 1

:error
echo Setup failed. Read the error above.
pause
exit /b 1
