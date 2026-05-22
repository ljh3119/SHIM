@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 949 >nul
cd /d "%~dp0"
set "PORT_ARG=%~1"
set "SECRET_FILE=%~dp0data\secret.key"

if not exist "%~dp0data" mkdir "%~dp0data" >nul 2>nul

if exist "%SECRET_FILE%" (
    set /p SHIM_SECRET_KEY=<"%SECRET_FILE%"
) else (
    echo Generating random SHIM_SECRET_KEY...
    for /f "usebackq tokens=*" %%F in (`powershell -NoProfile -Command "[Convert]::ToBase64String((1..32 | %% { [byte](Get-Random -Minimum 0 -Maximum 256) }))"`) do set "SHIM_SECRET_KEY=%%F"
    echo !SHIM_SECRET_KEY!>"%SECRET_FILE%"
    echo Secret saved to data\secret.key
)

if "!SHIM_SECRET_KEY!"=="" (
    echo Secret load failed. Check data\secret.key and try again.
    goto FAIL
)

set "START_PORT=8000"
if not "%PORT_ARG%"=="" (
    echo %PORT_ARG%| findstr /R "^[0-9][0-9]*$" >nul
    if not errorlevel 1 (
        set "START_PORT=%PORT_ARG%"
    )
)

set "MAX_PORT=8100"
set "CUR_PORT=%START_PORT%"

:PORT_SEARCH_LOOP
set "PORT_PID="
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%CUR_PORT% .*LISTENING"') do set "PORT_PID=%%A"

if "!PORT_PID!"=="" (
    set "PORT=%CUR_PORT%"
    goto PORT_SEARCH_DONE
) else (
    rem Port is in use. Check if it's SHIM_Portable.exe
    tasklist /FI "PID eq !PORT_PID!" | find /I "SHIM_Portable.exe" >nul 2>nul
    if not errorlevel 1 (
        echo SHIM_Portable is already running on port %CUR_PORT%.
        start "" http://localhost:%CUR_PORT%
        exit /b 0
    )
    set /a CUR_PORT+=1
    if !CUR_PORT! GTR %MAX_PORT% (
        echo No free ports found in range %START_PORT% - %MAX_PORT%.
        goto FAIL
    )
    goto PORT_SEARCH_LOOP
)

:PORT_SEARCH_DONE
echo Selected free port: %PORT%
set "SHIM_PORT=%PORT%"
set "SHIM_RUNTIME_BASE=%~dp0_internal"

:START_APP
start "" /b SHIM_Portable.exe
ping 127.0.0.1 -n 3 >nul
tasklist /FI "IMAGENAME eq SHIM_Portable.exe" | find /I "SHIM_Portable.exe" >nul 2>nul
if errorlevel 1 (
    echo Failed to start SHIM_Portable.
    echo Check security policy and try again.
    goto FAIL
)

echo SHIM_Portable started successfully on port %PORT%.
exit /b 0

:FAIL
echo.
echo Press any key to close...
pause >nul
exit /b 1
