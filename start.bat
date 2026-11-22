@echo off
setlocal EnableExtensions
set "CIVICONNECT_PROJECT_OPEN="
set "step=opening the project folder"
pushd "%~dp0" || goto failed
set "CIVICONNECT_PROJECT_OPEN=1"
set "step=checking Python 3.11 to 3.13"
if exist "venv\Scripts\python.exe" goto checkenv
set "PY_CMD="
for %%V in (3.13 3.12 3.11) do (
  if not defined PY_CMD (
    py -%%V -c "import sys" >nul 2>nul && set "PY_CMD=py -%%V"
  )
)
if not defined PY_CMD goto installpython
:makeenv
set "step=creating the Python environment"
%PY_CMD% -m venv venv || goto failed
:checkenv
set "PY=%~dp0venv\Scripts\python.exe"
"%PY%" -c "import sys; sys.exit(not ((3,11) <= sys.version_info[:2] <= (3,13)))" || goto wrongvenv
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
:installpython
where winget >nul 2>nul || goto nopython
echo Python 3.11, 3.12 or 3.13 was not found on this PC.
choice /c YN /m "Install Python 3.12 now using winget"
if errorlevel 2 goto nopython
set "step=installing Python 3.12"
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements || goto failed
set "PY_CMD="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY_CMD py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
if not defined PY_CMD goto restartneeded
goto makeenv
:restartneeded
echo Python was installed, but this window cannot see it yet.
echo Close this window and run start.bat again.
goto failed
:nopython
echo Python 3.11, 3.12 or 3.13 is required. Newer versions are not supported yet.
echo Install one from https://www.python.org/downloads/ and run start.bat again.
goto failed
:wrongvenv
echo The existing venv folder was built with an unsupported Python version.
echo Delete the venv folder and run start.bat again.
goto failed
:failed
echo CiviConnect failed while %step%.
if defined CIVICONNECT_PROJECT_OPEN popd
pause
exit /b 1