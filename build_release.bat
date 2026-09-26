@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :python_error

echo [1/5] Preparing bundled FFmpeg...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_ffmpeg.ps1"
if errorlevel 1 goto :error

echo [2/5] Installing build dependencies...
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo [3/5] Running checks...
python -m py_compile main.py engine.py i18n.py version.py test_core.py test_i18n.py test_render_integration.py test_release_layout.py
if errorlevel 1 goto :error
python test_core.py
if errorlevel 1 goto :error
python test_i18n.py
if errorlevel 1 goto :error
python test_render_integration.py
if errorlevel 1 goto :error
python test_release_layout.py
if errorlevel 1 goto :error

echo [4/5] Building autonomous executable...
python -m PyInstaller --noconfirm --clean --windowed --onefile --noupx --name "TikTok Split Maker" --icon "assets\icon.ico" --version-file "version_info.txt" --add-data "assets;assets" --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES.md;." --add-binary "vendor\ffmpeg\bin\ffmpeg.exe;ffmpeg\bin" --add-binary "vendor\ffmpeg\bin\ffprobe.exe;ffmpeg\bin" --additional-hooks-dir "." main.py
if errorlevel 1 goto :error

echo [5/5] Calculating SHA-256...
powershell -NoProfile -Command "Get-FileHash -Algorithm SHA256 'dist\TikTok Split Maker.exe' | Format-List"

echo.
echo Build complete: dist\TikTok Split Maker.exe
pause
exit /b 0

:python_error
echo.
echo Python was not found in PATH.
echo Install Python 3.12 x64 and enable "Add Python to PATH".
pause
exit /b 1

:error
echo.
echo Build failed. Read the error above.
pause
exit /b 1
