@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 949 >nul
cd /d "%~dp0"
set "PORT=%~1"
set "SECRET_FILE=%~dp0data\secret.key"

if "%PORT%"=="" (
    set /p PORT=Port [default 8000]:
)
if "%PORT%"=="" set "PORT=8000"

echo %PORT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 set "PORT=8000"
if %PORT% LSS 1 set "PORT=8000"
if %PORT% GTR 65535 set "PORT=8000"

echo Selected port: %PORT%
set "SHIM_PORT=%PORT%"
set "SHIM_RUNTIME_BASE=%~dp0_internal"

if not exist "%~dp0data" mkdir "%~dp0data" >nul 2>nul

if exist "%SECRET_FILE%" (
    set /p SHIM_SECRET_KEY=<"%SECRET_FILE%"
) else (
    echo.
    echo SHIM_SECRET_KEY not found.
    set /p SHIM_SECRET_KEY=Enter initial SHIM_SECRET_KEY ^(min 32 chars recommended^): 
    if "!SHIM_SECRET_KEY!"=="" (
        echo Empty secret is not allowed. Start cancelled.
        goto FAIL
    )
    >"%SECRET_FILE%" echo(!SHIM_SECRET_KEY!
    echo Secret saved to data\secret.key
)

if "!SHIM_SECRET_KEY!"=="" (
    echo Secret load failed. Check data\secret.key and try again.
    goto FAIL
)

set "PORT_PID="
for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "PORT_PID=%%A"
if "!PORT_PID!"=="" goto START_APP

tasklist /FI "PID eq !PORT_PID!" | find /I "SHIM_Portable.exe" >nul 2>nul
if errorlevel 1 (
    echo Port %PORT% is already in use by another process (PID=!PORT_PID!).
    echo Choose another port. Example: 8010
    goto FAIL
)
echo SHIM_Portable is already running on port %PORT%.
start "" http://localhost:%PORT%
exit /b 0

:START_APP
start "" /b SHIM_Portable.exe
ping 127.0.0.1 -n 3 >nul
tasklist /FI "IMAGENAME eq SHIM_Portable.exe" | find /I "SHIM_Portable.exe" >nul 2>nul
if errorlevel 1 (
    echo Failed to start SHIM_Portable.
    echo Check security policy and try again.
    goto FAIL
)

echo SHIM_Portable started.
start "" http://localhost:%PORT%
exit /b 0

:FAIL
echo.
echo Press any key to close...
pause >nul
exit /b 1
