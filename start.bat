@echo off
setlocal EnableExtensions
set "CIVICONNECT_PROJECT_OPEN="
set "step=opening the project folder"
pushd "%~dp0" || goto failed
set "CIVICONNECT_PROJECT_OPEN=1"
set "step=checking Python 3.11 or newer"
if exist "venv\Scripts\python.exe" goto checkenv
set "PY_CMD=py -3"
%PY_CMD% -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>nul
if not errorlevel 1 goto makeenv
set "PY_CMD=python"
%PY_CMD% -c "import sys; sys.exit(sys.version_info < (3,11))" || goto failed
:makeenv
set "step=creating the Python environment"
%PY_CMD% -m venv venv || goto failed
:checkenv
set "PY=%~dp0venv\Scripts\python.exe"
"%PY%" -c "import sys; sys.exit(sys.version_info < (3,11))" || goto failed
if /i "%~1"=="status" goto server_control
if /i "%~1"=="stop" goto server_control
title CiviConnect - Local server
echo Starting CiviConnect from "%~dp0"
set "step=installing Python dependencies"
echo Checking dependencies...
"%PY%" -m pip --disable-pip-version-check install -q -r requirements.txt || goto failed
set "step=creating config.json"
if not exist config.json copy /y config.example.json config.json >nul || goto failed
if "%~1"=="" goto serve
if /i "%~1"=="reset" goto manage
echo Usage: start.bat [status ^| stop ^| reset]
set "step=validating launcher arguments"
goto failed
:manage
set "step=preparing application data"
"%PY%" "py\manage.py" "%~1" || goto failed
:serve
echo Refreshing Athens representatives from OpenCouncil...
"%PY%" "py\manage.py" sync-athens || echo Warning: OpenCouncil refresh failed. Using the saved directory.
set "step=running the local web server"
"%PY%" -u "%~dp0py\launch.py" || goto failed
goto done
:server_control
set "step=checking the local web server"
"%PY%" -u "%~dp0py\launch.py" "%~1" || goto failed
:done
popd
exit /b 0
:failed
echo CiviConnect failed while %step%.
if defined CIVICONNECT_PROJECT_OPEN popd
pause
exit /b 1
