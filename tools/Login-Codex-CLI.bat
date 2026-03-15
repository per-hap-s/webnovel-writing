@echo off
setlocal EnableExtensions
title Codex CLI Login
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0Login-Codex-CLI.ps1" %*
