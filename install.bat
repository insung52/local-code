@echo off
chcp 65001 > nul
echo ========================================
echo   Local Code Assistant - Install
echo ========================================
echo.

set "INSTALL_PATH=%~dp0"
set "INSTALL_PATH=%INSTALL_PATH:~0,-1%"

echo Install path: %INSTALL_PATH%
echo.

echo Adding to PATH...
setx PATH "%PATH%;%INSTALL_PATH%" > nul 2>&1
echo Done.
echo.

echo Installing Python dependencies...
cd /d "%INSTALL_PATH%\client"
pip install -r requirements.txt -q
echo Done.
echo.

echo ========================================
echo   Installation complete!
echo ========================================
echo.
echo Open a NEW terminal and run:
echo   llmcode
echo.
pause
