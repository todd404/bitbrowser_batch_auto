@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "VENV_PY=%ROOT_DIR%.venv\Scripts\python.exe"
set "DEFAULT_CONFIG=configs\app.example.yaml"
set "MODE=desktop"
set "EXTRA_ARGS="

if "%~1"=="" goto ensure_venv
if /I "%~1"=="desktop" (
  set "MODE=desktop"
  shift
  goto collect_args
)
if /I "%~1"=="web" (
  set "MODE=web"
  shift
  goto collect_args
)
if /I "%~1"=="-h" goto usage
if /I "%~1"=="--help" goto usage
if /I "%~1"=="help" goto usage

echo Unknown mode: %~1
echo.
goto usage_error

:usage
echo Usage:
echo   start_windows.bat
echo   start_windows.bat desktop [extra ui args...]
echo   start_windows.bat web [extra ui args...]
echo.
echo Modes:
echo   desktop   Launch the native desktop UI ^(default^)
echo   web       Launch the web UI in the default browser
echo.
echo Examples:
echo   start_windows.bat
echo   start_windows.bat web --port 8765
echo   start_windows.bat desktop --host 127.0.0.1
exit /b 0

:usage_error
echo Usage:
echo   start_windows.bat
echo   start_windows.bat desktop [extra ui args...]
echo   start_windows.bat web [extra ui args...]
exit /b 1

:collect_args
if "%~1"=="" goto ensure_venv
set EXTRA_ARGS=%EXTRA_ARGS% "%~1"
shift
goto collect_args

:ensure_venv
cd /d "%ROOT_DIR%"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%ROOT_DIR%scripts\setup_venv.py"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found. Please install Python 3 first.
    exit /b 1
  )
  python "%ROOT_DIR%scripts\setup_venv.py"
)
if not %ERRORLEVEL%==0 exit /b %ERRORLEVEL%

if /I "%MODE%"=="web" (
  echo Starting bitbrowser-auto in web mode ...
  "%VENV_PY%" -m bitbrowser_auto ui --config "%DEFAULT_CONFIG%" --web %EXTRA_ARGS%
) else (
  echo Starting bitbrowser-auto in desktop mode ...
  "%VENV_PY%" -m bitbrowser_auto ui --config "%DEFAULT_CONFIG%" %EXTRA_ARGS%
)
exit /b %ERRORLEVEL%
