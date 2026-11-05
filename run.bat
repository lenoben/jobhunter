@echo off
rem Double-click me to open JobHunter after install.bat has run once. Keep this window open.
title JobHunter
cd /d "%~dp0ui"
if not exist build\handler.js (
    echo JobHunter is not installed yet. Double-click install.bat first.
    pause
    exit /b 1
)
echo JobHunter is starting. Your browser opens in a moment: http://localhost:5173
echo Keep this window open while you use it. Close it to stop JobHunter.
start "" /min cmd /c "timeout /t 4 >nul & start http://localhost:5173%~1"
call npm start
pause
