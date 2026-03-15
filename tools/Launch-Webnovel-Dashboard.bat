@echo off
setlocal EnableExtensions
title Webnovel Dashboard
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0Launch-Webnovel-Dashboard.ps1" %*
