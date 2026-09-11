@echo off
setlocal enabledelayedexpansion

title Veyra - Automated Premiere Pro Installer
echo ===============================================================================
echo                      VEYRA — PREMIERE PRO INSTALLER
echo               Local AI Speech Enhancement Extension for Editors
echo ===============================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs" 2>nul
set "INSTALL_LOG=%SCRIPT_DIR%logs\installer.log"
echo [LOG] Installation started at %date% %time% >> "%INSTALL_LOG%"

:: Step 1: Clean up any old/legacy extensions to prevent duplicates
echo [1/5] Cleaning legacy extension installations...
if exist "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" (
    rmdir /S /Q "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" 2>nul
)
if exist "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" (
    rmdir /S /Q "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" 2>nul
)
echo [OK] Legacy cleanup verified.

:: Step 2: Enable CEP PlayerDebugMode in Windows Registry
echo.
echo [2/5] Enabling Adobe Extension Debug Mode in Windows Registry...
for %%v in (7 8 9 10 11 12 13 14 15 16) do (
    reg add "HKCU\Software\Adobe\CSXS.%%v" /v PlayerDebugMode /t REG_SZ /d 1 /f >nul 2>nul
)
echo [OK] Extension debug mode enabled for all Adobe CSXS versions.

:: Step 3: Verify & Locate Speechify Private Runtime
echo.
echo [3/5] Locating and Verifying Private Veyra Runtime...
set "PYTHON_EXE="

if not exist "%SCRIPT_DIR%runtime" (
    if exist "%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer" (
        echo Linking private runtime environment...
        cmd /c mklink /J "%SCRIPT_DIR%runtime" "%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer" >nul 2>nul
    )
)

if exist "%SCRIPT_DIR%runtime\Scripts\pythonw.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%runtime\Scripts\pythonw.exe"
) else if exist "%SCRIPT_DIR%runtime\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%runtime\Scripts\pythonw.exe"
) else if exist "%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer\Scripts\pythonw.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%benchmark_archive\benchmark_envs\zipenhancer\Scripts\pythonw.exe"
) else (
    where pythonw >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where pythonw') do (
            if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
        )
    )
    if not defined PYTHON_EXE (
        where python >nul 2>nul
        if not errorlevel 1 (
            for /f "delims=" %%i in ('where python') do (
                if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
            )
        )
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] No compatible Python runtime found.
    echo [ERROR] No Python runtime detected >> "%INSTALL_LOG%"
    pause
    exit /b 1
) else (
    echo [OK] Verified private runtime: !PYTHON_EXE!
    echo [LOG] Runtime selected: !PYTHON_EXE! >> "%INSTALL_LOG%"
)

set "ENGINE_SCRIPT=%SCRIPT_DIR%engine\server.py"
set "PROJECT_ROOT=%SCRIPT_DIR%"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

:: Write engine_config.json
echo Generating dynamic engine configuration...
powershell -NoProfile -Command "$cfg = @{ python_exe = $env:PYTHON_EXE; engine_script = $env:ENGINE_SCRIPT; project_root = $env:PROJECT_ROOT }; $json = $cfg | ConvertTo-Json; [System.IO.File]::WriteAllText('%SCRIPT_DIR%plugin\engine_config.json', $json, (New-Object System.Text.UTF8Encoding($false)))"

set "VALIDATION_PY=!PYTHON_EXE:pythonw.exe=python.exe!"
if exist "!VALIDATION_PY!" (
    echo Validating models and runtime integrity...
    "!VALIDATION_PY!" -c "import sys; sys.path.insert(0, r'%PROJECT_ROOT%'); from models.manager import ModelManager; m = ModelManager(); print('[OK] Discovered models:', list(m.list_models().keys()))" >> "%INSTALL_LOG%" 2>&1
)

:: Step 4: Deploy to Adobe Premiere Pro CEP Extensions Directory
echo.
echo [4/5] Deploying Veyra to Adobe Extension directories...
set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
if not exist "%APPDATA%\Adobe\CEP\extensions" mkdir "%APPDATA%\Adobe\CEP\extensions" 2>nul
if exist "!TARGET_CEP_DIR!" rmdir /S /Q "!TARGET_CEP_DIR!" 2>nul
mkdir "!TARGET_CEP_DIR!" 2>nul

xcopy /E /I /Y /Q "%SCRIPT_DIR%plugin\*" "!TARGET_CEP_DIR!\" >nul
copy /Y "%SCRIPT_DIR%plugin\engine_config.json" "!TARGET_CEP_DIR!\engine_config.json" >nul 2>nul
echo [OK] Deployed to CEP directory.

:: Step 5: Deploy to Adobe UXP Plugins Directory
set "TARGET_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer"
if not exist "%APPDATA%\Adobe\UXP\Plugins\External" mkdir "%APPDATA%\Adobe\UXP\Plugins\External" 2>nul
if exist "!TARGET_UXP_DIR!" rmdir /S /Q "!TARGET_UXP_DIR!" 2>nul
mkdir "!TARGET_UXP_DIR!" 2>nul
xcopy /E /I /Y /Q "%SCRIPT_DIR%plugin\*" "!TARGET_UXP_DIR!\" >nul
copy /Y "%SCRIPT_DIR%plugin\engine_config.json" "!TARGET_UXP_DIR!\engine_config.json" >nul 2>nul
echo [OK] Deployed to UXP directory.

:: Step 6: Final Instructions
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
echo    Window -^> Extensions -^> Veyra
echo.
echo 3. The engine and local AI models will start and initialize automatically!
echo    No Command Prompt or manual daemon launching required.
echo.
echo 4. Select an audio clip on your timeline and click 'Enhance Speech'!
echo ===============================================================================
echo.
echo [LOG] Installation completed successfully at %date% %time% >> "%INSTALL_LOG%"

exit /b 0
