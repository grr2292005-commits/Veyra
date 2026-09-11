@echo off
setlocal enabledelayedexpansion

title Speechify - Uninstaller
echo ===============================================================================
echo                      SPEECHIFY — UNINSTALLER
echo ===============================================================================
echo.

set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
set "TARGET_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer"
set "LEGACY_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer"
set "LEGACY_UXP_DIR=%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer"

echo Removing Speechify from Adobe Premiere Pro extensions...

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
echo                   SPEECHIFY UNINSTALLED SUCCESSFULLY!
echo ===============================================================================
echo.
echo NOTE REGARDING AI MODEL WEIGHTS:
echo Your downloaded neural model weights in 'models\storage' were PRESERVED.
echo If you wish to delete them to reclaim disk space, you should manually delete
echo the following folder:
echo.
echo   "%~dp0..\models\storage"
echo.
echo ===============================================================================
echo.
pause
exit /b 0
