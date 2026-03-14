@echo off
setlocal EnableExtensions

set "TARGET=%~dp0webnovel-writer\Start-Webnovel-Writer.bat"
if not exist "%TARGET%" (
    echo Launcher not found:
    echo %TARGET%
    pause
    exit /b 1
)

call "%TARGET%" %*
