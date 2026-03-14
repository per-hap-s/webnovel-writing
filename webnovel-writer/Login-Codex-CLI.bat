@echo off
setlocal EnableExtensions
title Codex CLI Login

set "CODEX_CMD=%APPDATA%\npm\codex.cmd"
set "NODE_DIR=%LOCALAPPDATA%\Programs\NodePortable"
set "PATH=%APPDATA%\npm;%NODE_DIR%;%PATH%"

if not exist "%CODEX_CMD%" (
    echo Codex CLI not found.
    echo Expected: %CODEX_CMD%
    echo.
    pause
    exit /b 1
)

echo Starting Codex CLI login...
echo.
"%CODEX_CMD%" login
echo.
"%CODEX_CMD%" login status
echo.
pause
