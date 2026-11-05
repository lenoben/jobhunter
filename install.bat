@echo off
rem Double-click me: installs JobHunter, asks for your settings and starts it (see README).
title JobHunter installer
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 pause
