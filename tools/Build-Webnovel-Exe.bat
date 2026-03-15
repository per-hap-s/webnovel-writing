@echo off
setlocal EnableExtensions
title Build Webnovel EXE
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0Build-Webnovel-Exe.ps1" %*
