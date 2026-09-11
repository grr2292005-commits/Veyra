@echo off
setlocal enabledelayedexpansion

title Speechify - Automated Premiere Pro Installer
echo ===============================================================================
echo                   SPEECHIFY — PREMIERE PRO INSTALLER
echo               Local AI Speech Enhancement Extension for Editors
echo ===============================================================================
echo.

set "SCRIPT_DIR=%~dp0..\ "
cd /d "%SCRIPT_DIR%"

if exist "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" (
    rmdir /S /Q "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" 2>nul
)
if exist "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" (
    rmdir /S /Q "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" 2>nul
)

echo [1/5] Enabling Adobe Extension Debug Mode in Windows Registry...
for %%v in (7 8 9 10 11 12 13 14 15 16) do (
    reg add "HKCU\Software\Adobe\CSXS.%%v" /v PlayerDebugMode /t REG_SZ /d 1 /f >nul 2>nul
)
echo [OK] Extension debug mode enabled for all Adobe CSXS versions.

echo.
echo [2/5] Deploying Speechify to Adobe CEP Extensions directory...
set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
echo Destination Path: !TARGET_CEP_DIR!

if not exist "%APPDATA%\Adobe\CEP\extensions" (
    mkdir "%APPDATA%\Adobe\CEP\extensions" 2>nul
)
if exist "!TARGET_CEP_DIR!" (
    rmdir /S /Q "!TARGET_CEP_DIR!" 2>nul
)
mkdir "!TARGET_CEP_DIR!" 2>nul

xcopy /E /I /Y /Q "%SCRIPT_DIR%plugin\*" "!TARGET_CEP_DIR!\" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy extension to Adobe CEP directory.
    pause
    exit /b 1
)
echo [OK] Speechify successfully deployed to:
echo      !TARGET_CEP_DIR!

echo.
echo [3/5] Deploying to Adobe UXP Plugins directory...
set "TARGET_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer"
if not exist "%APPDATA%\Adobe\UXP\Plugins\External" (
    mkdir "%APPDATA%\Adobe\UXP\Plugins\External" 2>nul
)
if exist "!TARGET_UXP_DIR!" (
    rmdir /S /Q "!TARGET_UXP_DIR!" 2>nul
)
mkdir "!TARGET_UXP_DIR!" 2>nul
xcopy /E /I /Y /Q "%SCRIPT_DIR%plugin\*" "!TARGET_UXP_DIR!\" >nul
echo [OK] Deployed to UXP directory.

echo.
echo [4/5] Verifying Local AI Engine Python Environment...
set "PYTHON_EXE="

if exist "%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where python') do (
            if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
        )
    )
)

if not defined PYTHON_EXE (
    echo [WARNING] No Python runtime automatically detected.
) else (
    echo [OK] Found Python runtime: !PYTHON_EXE!
    echo Initializing model storage registry...
    "!PYTHON_EXE!" -c "import sys; sys.path.insert(0, r'%SCRIPT_DIR%'); from models.manager import ModelManager; m = ModelManager(); print('Model Storage Root:', m.get_storage_path())"
)

echo.
echo [5/5] Finalizing Installation...
echo ===============================================================================
echo                      INSTALLATION SUCCESSFUL!
echo ===============================================================================
echo.
echo IMPORTANT: If Adobe Premiere Pro is currently open, please RESTART Premiere Pro
echo so it detects the newly installed extension.
echo.
echo TO USE:
echo 1. Open Adobe Premiere Pro.
echo.
echo 2. Navigate to:
echo    Window -^> Extensions -^> Speechify
echo.
echo 3. The engine and local AI models will start and initialize automatically!
echo    No Command Prompt or manual daemon launching required.
echo.
echo 4. Select an audio clip on your timeline and click 'Enhance Speech'!
echo ===============================================================================
echo.

pause
exit /b 0
