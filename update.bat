@echo off
rem Double-click me: gets the newest JobHunter and installs it. Your settings, profile and jobs are kept.
title JobHunter update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if errorlevel 1 pause
