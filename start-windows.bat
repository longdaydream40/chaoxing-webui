@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\start.ps1" -OpenBrowser

echo.
echo Chaoxing WebUI is starting.
echo Frontend: http://127.0.0.1:5501/
echo Backend:  http://127.0.0.1:8000/
echo.
echo Use deploy\stop.ps1 to stop services.
pause
