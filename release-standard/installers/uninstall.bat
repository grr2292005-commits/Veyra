@echo off
setlocal enabledelayedexpansion

title Veyra - Standard Uninstaller
echo ===============================================================================
echo                        VEYRA — UNINSTALLER
echo ===============================================================================
echo.

set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
set "TARGET_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer"
set "LEGACY_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer"
set "LEGACY_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer"
set "VEYRA_DIR=%LOCALAPPDATA%\Veyra"

echo Stopping any active Veyra background engine process...
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8765/shutdown' -Method POST -TimeoutSec 1 >$null } catch {}"

echo Removing Veyra from Adobe Premiere Pro extensions...

if exist "!TARGET_CEP_DIR!" (
    rmdir /S /Q "!TARGET_CEP_DIR!" 2>nul
    echo [OK] Removed from Adobe CEP extensions directory.
)
if exist "!TARGET_UXP_DIR!" (
    rmdir /S /Q "!TARGET_UXP_DIR!" 2>nul
    echo [OK] Removed from Adobe UXP plugins directory.
)
if exist "!LEGACY_CEP_DIR!" (
    rmdir /S /Q "!LEGACY_CEP_DIR!" 2>nul
)
if exist "!LEGACY_UXP_DIR!" (
    rmdir /S /Q "!LEGACY_UXP_DIR!" 2>nul
)

echo.
echo ===============================================================================
echo                     VEYRA UNINSTALLED SUCCESSFULLY!
echo ===============================================================================
echo.
echo NOTE REGARDING AI MODEL WEIGHTS & RUNTIME:
echo Your downloaded neural model weights and private runtime in:
echo   %LOCALAPPDATA%\Veyra
echo were PRESERVED so you do not need to re-download them if you reinstall.
echo.
echo To completely delete the runtime and model weights, delete:
echo   %LOCALAPPDATA%\Veyra
echo.
pause
exit /b 0
