@echo off
rem ---------------------------------------------------------------------------
rem  Builds the portable SlideCatch folder and its zip file (Windows 10/11).
rem
rem  Double-click this file, or run it from a command prompt. It needs Python
rem  3.10 or newer from python.org ("Add python.exe to PATH" ticked).
rem
rem  Steps: virtual environment (.venv) - tools - tests - build - self-test - zip
rem  Result: dist\SlideCatch\SlideCatch.exe and dist\SlideCatch-<version>-portable.zip
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0\.."

if not exist .venv\Scripts\python.exe (
    echo Creating the virtual environment .venv ...
    python -m venv .venv || goto :error
)
set "PY=.venv\Scripts\python.exe"

echo.
echo [1/5] Installing the tools ...
"%PY%" -m pip install --quiet --upgrade pip
"%PY%" -m pip install --quiet -r requirements-dev.txt || goto :error

echo [2/5] Running the tests ...
"%PY%" -m pytest || goto :error

echo [3/5] Building SlideCatch.exe ...
"%PY%" -m PyInstaller SlideCatch.spec --noconfirm --clean --log-level WARN || goto :error

echo [4/5] Checking the built program ...
rem "start /wait" waits for a window program and gives back its exit code
start "" /wait "dist\SlideCatch\SlideCatch.exe" --self-test "%CD%\dist\selftest.json"
if errorlevel 1 (
    echo The self-test failed. Details: dist\selftest.json
    goto :error
)

echo [5/5] Making the zip ...
rem (%PY% is a relative path without spaces: no quotes, "for /f" mishandles them)
for /f "delims=" %%v in ('%PY% -c "import slidecatch; print(slidecatch.APP_VERSION)"') do set "VERSION=%%v"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\SlideCatch' -DestinationPath 'dist\SlideCatch-%VERSION%-portable.zip' -Force" || goto :error

echo.
echo Done: dist\SlideCatch-%VERSION%-portable.zip
if not "%~1"=="--no-pause" pause
exit /b 0

:error
echo.
echo Build stopped - see the messages above.
if not "%~1"=="--no-pause" pause
exit /b 1
