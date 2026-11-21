@echo off
setlocal EnableExtensions
set "LOGDIR=%LOCALAPPDATA%\CiviConnect"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
set "LOGFILE=%LOGDIR%\start-%RANDOM%-%RANDOM%.log"
if not exist "%LOGDIR%" set "LOGFILE=%TEMP%\CiviConnect-start-%RANDOM%-%RANDOM%.log"
echo Starting CiviConnect...
echo Startup log: "%LOGFILE%"
>>"%LOGFILE%" echo [%date% %time%] Launching from "%~dp0"
set "step=opening the project folder"
pushd "%~dp0" 2>>"%LOGFILE%" || goto failed
set "step=checking Python 3.11 or newer"
if exist "venv\Scripts\python.exe" goto checkenv
set "PY_CMD=py -3"
%PY_CMD% -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>>"%LOGFILE%"
if not errorlevel 1 goto makeenv
set "PY_CMD=python"
%PY_CMD% -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>>"%LOGFILE%" || goto failed
:makeenv
set "step=creating the Python environment"
%PY_CMD% -m venv venv >>"%LOGFILE%" 2>&1 || goto failed
:checkenv
set "PY=venv\Scripts\python.exe"
"%PY%" -c "import sys; sys.exit(sys.version_info < (3,11))" 2>>"%LOGFILE%" || goto failed
set "step=installing Python dependencies"
echo Checking dependencies...
"%PY%" -m pip --disable-pip-version-check install -q -r requirements.txt >>"%LOGFILE%" 2>&1 || goto failed
set "step=creating config.json"
if not exist config.json copy /y config.example.json config.json >nul 2>>"%LOGFILE%" || goto failed
if "%~1"=="" goto serve
if /i "%~1"=="demo" goto manage
if /i "%~1"=="reset" goto manage
echo Usage: start.bat [demo^|reset]
set "step=validating launcher arguments"
goto failed
:manage
set "step=preparing application data"
"%PY%" manage.py "%~1" 2>>"%LOGFILE%" || goto failed
:serve
set "step=starting the local web server"
"%PY%" -u launch.py 2>>"%LOGFILE%" || goto failed
exit /b 0
:failed
echo CiviConnect failed while %step%.
>>"%LOGFILE%" echo [%date% %time%] Failed while %step%.
echo See "%LOGFILE%" for details.
pause
exit /b 1
