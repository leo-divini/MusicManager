@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  MusicManager - setup.bat
::
::  First run  : checks Python 3.11, creates .venv, installs
::               dependencies, and guides you through config.
::  Later runs : menu to edit settings or update dependencies.
:: ============================================================

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "REQUIREMENTS=%ROOT%Backend\requirements.txt"
set "WIZARD=%ROOT%setup_config.py"

echo.
echo  +==============================================+
echo  ^|        MusicManager  -  Setup / Config      ^|
echo  +==============================================+
echo.

:: --- Locate Python 3.11 --------------------------------------------
set "PYTHON="

py -3.11 --version >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON=py -3.11"
    goto :python_found
)

python --version 2>&1 | findstr /r "3\.11\." >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON=python"
    goto :python_found
)

python3 --version 2>&1 | findstr /r "3\.11\." >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON=python3"
    goto :python_found
)

echo  [ERROR] Python 3.11 was not found on this system.
echo.
echo  Download it from:
echo    https://www.python.org/downloads/release/python-3119/
echo.
echo  During installation, check "Add Python to PATH".
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%V in ('!PYTHON! --version 2^>^&1') do echo  [OK] Found %%V

:: --- First run: venv does not exist yet ----------------------------
if not exist "%VENV%\Scripts\activate.bat" (
    echo.
    echo  [1/3] Creating virtual environment in .venv ...
    !PYTHON! -m venv "%VENV%"
    if !errorlevel! neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo  [OK] Virtual environment ready.

    echo.
    echo  [2/3] Installing dependencies ...
    "%VENV_PIP%" install --upgrade pip --quiet
    "%VENV_PIP%" install -r "%REQUIREMENTS%"
    if !errorlevel! neq 0 (
        echo  [ERROR] Dependency installation failed.
        pause & exit /b 1
    )
    echo  [OK] Dependencies installed.

    echo.
    echo  [3/3] First-time configuration ...
    echo.
    "%VENV_PY%" "%WIZARD%"

    echo.
    echo  Setup complete!
    echo  Run setup.bat again any time to change settings.
    echo.
    pause
    exit /b 0
)

:: --- Subsequent runs: show menu ------------------------------------
:menu
echo  Virtual environment : %VENV%
echo.
echo  What would you like to do?
echo.
echo    [1] Edit settings   (config.yaml)
echo    [2] Update / reinstall dependencies
echo    [3] Exit
echo.
set /p "CHOICE= Choose [1-3]: "
echo.

if "!CHOICE!"=="1" goto :edit_config
if "!CHOICE!"=="2" goto :update_deps
if "!CHOICE!"=="3" goto :end

echo  Invalid choice - please enter 1, 2 or 3.
echo.
goto :menu

:edit_config
"%VENV_PY%" "%WIZARD%"
echo.
goto :menu

:update_deps
echo  Updating dependencies ...
"%VENV_PIP%" install --upgrade pip --quiet
"%VENV_PIP%" install -r "%REQUIREMENTS%"
if !errorlevel! neq 0 (
    echo  [ERROR] Update failed.
) else (
    echo  [OK] Dependencies updated.
)
echo.
goto :menu

:end
endlocal
