@echo off
chcp 949 >nul
cd /d "%~dp0"

taskkill /IM SHIM_Portable.exe /T /F >nul 2>nul
ping 127.0.0.1 -n 2 >nul
tasklist /FI "IMAGENAME eq SHIM_Portable.exe" | find /I "SHIM_Portable.exe" >nul 2>nul
if errorlevel 1 (
    echo SHIM_Portable stopped.
) else (
    echo Some processes may still remain. Check Task Manager for SHIM_Portable.exe.
)
