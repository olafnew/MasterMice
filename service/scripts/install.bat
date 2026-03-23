@echo off
echo MasterMice Service Installer
echo ============================
echo.

:: Check for admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Run this as Administrator
    pause
    exit /b 1
)

:: Find the exe relative to this script
set "SVC_EXE=%~dp0..\mastermice-svc.exe"
if not exist "%SVC_EXE%" (
    echo ERROR: mastermice-svc.exe not found at %SVC_EXE%
    pause
    exit /b 1
)

"%SVC_EXE%" install
if %errorlevel% neq 0 (
    echo.
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Service installed. Start with: sc start MasterMice
pause
