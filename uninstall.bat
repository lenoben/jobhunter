@echo off
rem Double-click me to remove JobHunter's scheduled runs and installed packages (see README).
title JobHunter uninstaller
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
pause
