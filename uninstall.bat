@echo off
setlocal enabledelayedexpansion

title Veyra - Uninstaller
echo ===============================================================================
echo                        VEYRA — UNINSTALLER
echo ===============================================================================
echo.

set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
set "TARGET_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer"
set "LEGACY_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer"
set "LEGACY_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer"

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
echo NOTE REGARDING AI MODEL WEIGHTS:
echo Your downloaded neural model weights in 'models\storage' were PRESERVED.
echo If you wish to delete them to reclaim disk space, you should manually delete
echo the following folder:
echo.
echo   "%~dp0models\storage"
echo.
echo ===============================================================================
echo.
pause
exit /b 0
