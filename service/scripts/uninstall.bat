@echo off
echo MasterMice Service Uninstaller
echo ===============================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Run this as Administrator
    pause
    exit /b 1
)

set "SVC_EXE=%~dp0..\mastermice-svc.exe"
if not exist "%SVC_EXE%" (
    echo ERROR: mastermice-svc.exe not found at %SVC_EXE%
    pause
    exit /b 1
)

"%SVC_EXE%" uninstall
pause
