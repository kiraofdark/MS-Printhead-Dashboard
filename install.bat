@echo off
setlocal EnableDelayedExpansion

set "INSTALL_DIR=%~dp0"
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

set "APP_NAME=MS Printhead Dashboard"
set "TASK_NAME=MS_Printhead_Snapshot"
set "START_BAT=!INSTALL_DIR!\start.bat"
set "SHORTCUT=%USERPROFILE%\Desktop\MS Printhead Dashboard.lnk"

::  Check Admin 
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

echo.
echo ================================================
echo   MS Printhead Dashboard -- Installer
echo ================================================
echo.
echo   Install dir: !INSTALL_DIR!
echo.

::  [1/5] Check Python
echo [1/5] Checking Python...
set PYTHON_EXE=

:: Try py launcher first (installed by python.org installer)
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "usebackq delims=" %%p in (`where py`) do (
        set PYTHON_EXE=%%p
        goto :check_python_ver
    )
)

:: Fallback to python (will check for WindowsApps stub below)
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "usebackq delims=" %%p in (`where python`) do (
        set PYTHON_EXE=%%p
        goto :check_python_ver
    )
)

echo.
echo   ERROR: Python not found.
echo   Download: https://www.python.org/downloads/
echo   Check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:check_python_ver
:: Check if it's the Windows Store stub (not real Python)
echo !PYTHON_EXE! | findstr /i "WindowsApps" >nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo   ERROR: The "python" found is a Windows Store stub, not real Python.
    echo   Path: !PYTHON_EXE!
    echo.
    echo   Fix - choose ONE of the following:
    echo.
    echo   [A] Install real Python from https://www.python.org/downloads/
    echo       Make sure to check "Add Python to PATH" during install.
    echo.
    echo   [B] Disable the App execution alias:
    echo       Settings ^> Apps ^> Advanced app settings
    echo       ^> App execution aliases ^> turn OFF python.exe and python3.exe
    echo       Then re-run this installer.
    echo.
    pause
    exit /b 1
)

:: Verify Python actually runs
"!PYTHON_EXE!" --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ERROR: Python found but cannot run: !PYTHON_EXE!
    echo   Try reinstalling from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('"!PYTHON_EXE!" --version 2^>^&1') do set PY_VER=%%v
echo        Python !PY_VER! -- !PYTHON_EXE!

::  [2/5] pip install 
echo.
echo [2/5] Installing Python packages...
"!PYTHON_EXE!" -m pip install --upgrade pip --quiet
"!PYTHON_EXE!" -m pip install -r "!INSTALL_DIR!\requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ERROR: pip install failed.
    pause
    exit /b 1
)
echo        Packages installed OK

::  [3/5] Init Database 
echo.
echo [3/5] Initializing database...
"!PYTHON_EXE!" -c "import sys; sys.path.insert(0, r'!INSTALL_DIR!'); import app; app.init_db()"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ERROR: Database init failed.
    pause
    exit /b 1
)
echo        Database ready

::  [4/5] Task Scheduler 
echo.
echo [4/5] Registering Task Scheduler (every 2 hours)...

schtasks /delete /tn "!TASK_NAME!" /f >nul 2>&1

:: Write PowerShell script to temp file (avoid ^ continuation issues)
set "PS_TEMP=%TEMP%\ms_task_reg.ps1"
(
    echo $exe    = '!PYTHON_EXE!'
    echo $script = '!INSTALL_DIR!\save_snapshot.py'
    echo $action = New-ScheduledTaskAction -Execute $exe -Argument "`"$script`""
    echo $trigger = New-ScheduledTaskTrigger -Once -At ([datetime]::Today^) -RepetitionInterval ([TimeSpan]::FromHours(2^)^) -RepetitionDuration ([TimeSpan]::MaxValue^)
    echo $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero^) -StartWhenAvailable $true
    echo Register-ScheduledTask -TaskName '!TASK_NAME!' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force -ErrorAction Stop
) > "!PS_TEMP!"

powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_TEMP!" >nul 2>&1
del "!PS_TEMP!" >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo        Task Scheduler registered
    echo.
    echo        Running first snapshot...
    "!PYTHON_EXE!" "!INSTALL_DIR!\save_snapshot.py"
) else (
    echo   WARNING: Task Scheduler failed -- run setup_task.bat manually later.
)

::  [5/5] start.bat + Desktop shortcut 
echo.
echo [5/5] Creating start.bat and Desktop shortcut...

(
    echo @echo off
    echo setlocal
    echo set "DIR=!INSTALL_DIR!"
    echo echo Starting MS Printhead Dashboard...
    echo start "MS Printhead" "!PYTHON_EXE!" "!INSTALL_DIR!\app.py"
    echo timeout /t 2 /nobreak ^>nul
    echo start http://localhost:5000
    echo endlocal
) > "!START_BAT!"

:: Write shortcut PowerShell to temp file
set "PS_TEMP=%TEMP%\ms_shortcut.ps1"
(
    echo $ws = New-Object -ComObject WScript.Shell
    echo $sc = $ws.CreateShortcut('!SHORTCUT!'^)
    echo $sc.TargetPath = '!START_BAT!'
    echo $sc.WorkingDirectory = '!INSTALL_DIR!'
    echo $sc.IconLocation = 'shell32.dll,137'
    echo $sc.Description = 'MS Printhead Dashboard'
    echo $sc.Save(^)
) > "!PS_TEMP!"

powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_TEMP!" >nul 2>&1
del "!PS_TEMP!" >nul 2>&1

if exist "!SHORTCUT!" (
    echo        Desktop shortcut created
) else (
    echo   WARNING: Could not create shortcut -- use start.bat directly.
)

::  Done 
echo.
echo ================================================
echo   Installation Complete!
echo ================================================
echo.
echo   Start : double-click "MS Printhead Dashboard" on Desktop
echo        or run start.bat
echo.
echo   URL   : http://localhost:5000
echo.
echo   Snapshot: Task Scheduler runs every 2 hours automatically
echo.

set /p LAUNCH=   Launch now? [Y/N]:
if /i "!LAUNCH!"=="Y" call "!START_BAT!"

echo.
pause
endlocal
