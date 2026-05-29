@echo off
setlocal EnableDelayedExpansion

:: Edit these two lines before running
set "GITHUB_USERNAME=kiraofdark"
set "REPO_NAME=MS-Printhead-Dashboard"

set "REPO_URL=https://github.com/%GITHUB_USERNAME%/%REPO_NAME%.git"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

echo.
echo ================================================
echo   MS Printhead Dashboard -- Push to GitHub
echo ================================================
echo   Repo : %REPO_URL%
echo   Dir  : %DIR%
echo.

cd /d "%DIR%"

:: Check git
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Git not found.
    echo         Download: https://git-scm.com/download/win
    pause & exit /b 1
)

:: Init repo
if not exist ".git" (
    echo [1/4] Initializing git repo...
    git init
    git branch -M main
) else (
    echo [1/4] Git repo already initialized.
)

:: Set remote
echo.
echo [2/4] Setting remote origin...
git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%

:: Stage all files (respects .gitignore automatically)
echo.
echo [3/4] Staging all files...
git add .
git status

:: Commit
echo.
echo [4/4] Committing and pushing...
git commit -m "Add all project files"
git push -u origin main --force

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================
    echo   SUCCESS!
    echo   %REPO_URL%
    echo ================================================
) else (
    echo.
    echo [ERROR] Push failed. Check:
    echo   1. Repo exists on GitHub
    echo   2. GITHUB_USERNAME and REPO_NAME are correct
    echo   3. Use Personal Access Token as password
    echo      Create token: https://github.com/settings/tokens
)

echo.
pause
endlocal
