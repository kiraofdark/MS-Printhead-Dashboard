@echo off
setlocal
set "DIR=D:\python\Launch OK\Launch OK\mockup data"
echo Starting MS Printhead Dashboard...
start "MS Printhead" "C:\Windows\py.exe" "D:\python\Launch OK\Launch OK\mockup data\app.py"
timeout /t 2 /nobreak >nul
start http://localhost:5000
endlocal
