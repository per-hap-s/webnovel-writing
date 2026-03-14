@echo off
setlocal EnableExtensions
title Webnovel Writer
powershell -ExecutionPolicy Bypass -File "%~dp0Start-Webnovel-Writer.ps1" %*
