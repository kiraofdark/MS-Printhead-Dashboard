@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "INSTALL_DIR=%~dp0"
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

set "TASK_NAME=MS_Printhead_Snapshot"

:: ── ตรวจสิทธิ์ Admin ─────────────────────────────────
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  ขอ Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

for /f "usebackq delims=" %%p in (`where python`) do (
    set PYTHON_EXE=%%p
    goto :got_python
)
:got_python

echo.
echo  Registering Task Scheduler: !TASK_NAME!
echo  Script : !INSTALL_DIR!\save_snapshot.py
echo  Python : !PYTHON_EXE!
echo  Schedule: Every 2 hours
echo.

schtasks /delete /tn "!TASK_NAME!" /f >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$exe    = '!PYTHON_EXE!'; ^
   $script = '!INSTALL_DIR!\save_snapshot.py'; ^
   $action = New-ScheduledTaskAction -Execute $exe -Argument ('\"{0}\"' -f $script); ^
   $trigger = New-ScheduledTaskTrigger -Once -At ([datetime]::Today) -RepetitionInterval ([TimeSpan]::FromHours(2)) -RepetitionDuration ([TimeSpan]::MaxValue); ^
   $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable $true; ^
   Register-ScheduledTask -TaskName '!TASK_NAME!' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force -ErrorAction Stop"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo  SUCCESS: Task registered!
    echo.
    echo  Running snapshot now...
    "!PYTHON_EXE!" "!INSTALL_DIR!\save_snapshot.py"
    echo.
    echo  ตรวจสอบ Task:
    echo    schtasks /query /tn "!TASK_NAME!" /fo LIST
) else (
    echo.
    echo  ERROR: ลงทะเบียนไม่ได้ — ลองรันด้วยสิทธิ์ Administrator
)

pause
endlocal
