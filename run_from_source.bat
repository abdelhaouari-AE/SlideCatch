@echo off
rem ---------------------------------------------------------------------------
rem  Starts SlideCatch from the source code (for development and testing).
rem  The first run prepares a virtual environment (.venv) with the libraries.
rem  Needs Python 3.10 or newer from python.org ("Add python.exe to PATH").
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo First start: preparing Python and the libraries, please wait ...
    python -m venv .venv || goto :error
    .venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt || goto :error
)
.venv\Scripts\python.exe main.py %*
exit /b %errorlevel%

:error
echo.
echo Could not prepare Python. Is Python 3.10 or newer installed and on the PATH?
pause
exit /b 1
