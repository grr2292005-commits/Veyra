@echo off
setlocal enabledelayedexpansion

title Veyra - Automated Premiere Pro Installer
echo ===============================================================================
echo                      VEYRA — PREMIERE PRO INSTALLER
echo             Local AI Speech Enhancement for Adobe Premiere Pro
echo ===============================================================================
echo.

:: 1. Verify Windows 64-bit Architecture
if not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if not "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
    echo [ERROR] Veyra requires 64-bit Windows.
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%..\engine\server.py" set "SCRIPT_DIR=%SCRIPT_DIR%..\"
cd /d "%SCRIPT_DIR%"

:: 2. Setup Isolated Veyra Directories in %LOCALAPPDATA%\Veyra
if not defined VEYRA_DIR set "VEYRA_DIR=%LOCALAPPDATA%\Veyra"
set "RUNTIME_DIR=%VEYRA_DIR%\runtime"
set "MODELS_DIR=%VEYRA_DIR%\models"
set "CACHE_DIR=%VEYRA_DIR%\cache"
set "CONFIG_DIR=%VEYRA_DIR%\config"
set "LOGS_DIR=%VEYRA_DIR%\logs"

if not exist "%VEYRA_DIR%" mkdir "%VEYRA_DIR%" 2>nul
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" 2>nul
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%" 2>nul
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%" 2>nul
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%" 2>nul
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%" 2>nul

set "INSTALL_LOG=%LOGS_DIR%\installer.log"
echo [LOG] Veyra Installation started at %date% %time% >> "%INSTALL_LOG%"

:: 3. Dynamic Hardware Detection
echo [1/6] Detecting System Hardware & AI Acceleration Capabilities...
set "HAS_NVIDIA="
set "GPU_NAME=CPU"
set "GPU_VRAM="
set "REQ_FILE=%SCRIPT_DIR%requirements-standard-cpu.txt"

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    for /f "tokens=1,2 delims=," %%a in ('nvidia-smi --query-gpu^=name^,memory.total --format^=csv^,noheader 2^>nul') do (
        set "GPU_NAME=%%a"
        set "GPU_VRAM=%%b"
        set "HAS_NVIDIA=1"
    )
)

if not defined HAS_NVIDIA (
    for /f "usebackq delims=" %%g in (`powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like '*NVIDIA*' }).Name" 2^>nul`) do (
        if not "%%g"=="" (
            set "GPU_NAME=%%g"
            set "HAS_NVIDIA=1"
        )
    )
)

if defined HAS_NVIDIA (
    echo [OK] Detected NVIDIA GPU: !GPU_NAME!
    if defined GPU_VRAM echo      VRAM: !GPU_VRAM!
    echo [OK] Hardware Profile: NVIDIA CUDA Accelerated
    set "REQ_FILE=%SCRIPT_DIR%requirements-standard-cuda.txt"
) else (
    echo [OK] No NVIDIA GPU detected.
    echo [OK] Hardware Profile: Multi-Core CPU
    set "REQ_FILE=%SCRIPT_DIR%requirements-standard-cpu.txt"
)

:: 4. Provision Isolated Private Python Runtime
echo.
echo [2/6] Provisioning Isolated Private Python Runtime in Veyra Directory...
set "PYTHON_EXE="
set "PYTHONW_EXE="

if exist "%RUNTIME_DIR%\python.exe" (
    set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
    set "PYTHONW_EXE=%RUNTIME_DIR%\pythonw.exe"
) else if exist "%RUNTIME_DIR%\Scripts\python.exe" (
    set "PYTHON_EXE=%RUNTIME_DIR%\Scripts\python.exe"
    set "PYTHONW_EXE=%RUNTIME_DIR%\Scripts\pythonw.exe"
)

set "RUNTIME_READY="
if defined PYTHON_EXE (
    "!PYTHON_EXE!" -c "import sys; import torch; import soundfile" >nul 2>nul
    if not errorlevel 1 (
        echo [OK] Validated existing private runtime at:
        echo      !RUNTIME_DIR!
        set "RUNTIME_READY=1"
    )
)

if not defined RUNTIME_READY (
    if not defined PYTHON_EXE (
        echo Downloading deterministic Python 3.11 standalone runtime...
        set "PY_STANDALONE_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20240415/cpython-3.11.9%%2B20240415-x86_64-pc-windows-msvc-shared-install_only.tar.gz"
        set "PY_ARCHIVE=%CACHE_DIR%\cpython-3.11.9.tar.gz"
        
        powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('!PY_STANDALONE_URL!', '!PY_ARCHIVE!') } catch { exit 1 }"
        if errorlevel 1 (
            echo Standalone download failed, downloading official Python installer...
            set "PY_INSTALLER=%CACHE_DIR%\python-3.11.9-amd64.exe"
            powershell -NoProfile -Command "(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '!PY_INSTALLER!')"
            "!PY_INSTALLER!" /quiet InstallAllUsers=0 TargetDir="%RUNTIME_DIR%" Include_launcher=0 Shortcuts=0 PrependPath=0
        ) else (
            echo Extracting private runtime...
            tar.exe -xzf "!PY_ARCHIVE!" -C "%RUNTIME_DIR%" --strip-components=1 2>nul
            if errorlevel 1 (
                powershell -NoProfile -Command "tar -xzf '!PY_ARCHIVE!' -C '%RUNTIME_DIR%' --strip-components=1"
            )
        )
        
        if exist "%RUNTIME_DIR%\python.exe" (
            set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
            set "PYTHONW_EXE=%RUNTIME_DIR%\pythonw.exe"
        ) else if exist "%RUNTIME_DIR%\Scripts\python.exe" (
            set "PYTHON_EXE=%RUNTIME_DIR%\Scripts\python.exe"
            set "PYTHONW_EXE=%RUNTIME_DIR%\Scripts\pythonw.exe"
        )
    )

    if not defined PYTHON_EXE (
        echo [ERROR] Failed to provision private Python runtime in !RUNTIME_DIR!
        pause
        exit /b 1
    )

    echo [OK] Private runtime provisioned: !PYTHON_EXE!

    :: 5. Install Pinned Dependencies into Private Runtime
    echo.
    echo [3/6] Installing Pinned Dependencies into Private Runtime...
    "!PYTHON_EXE!" -m pip install --upgrade pip --quiet --no-warn-script-location
    
    echo Installing production packages from !REQ_FILE!...
    "!PYTHON_EXE!" -m pip install -r "!REQ_FILE!" --quiet --no-warn-script-location
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [OK] All production dependencies installed into private runtime.
) else (
    echo [3/6] Private runtime dependencies already satisfied.
)

:: 6. Verify PyTorch and Hardware Backend
echo.
echo [4/6] Verifying PyTorch and Hardware Acceleration Backend...
"!PYTHON_EXE!" -c "import torch; print(f'[OK] PyTorch {torch.__version__} | CUDA Available: {torch.cuda.is_available()}')"
if errorlevel 1 (
    echo [ERROR] PyTorch verification failed.
    pause
    exit /b 1
)

:: 7. Deploy Extension to Adobe Premiere Pro
echo.
echo [5/6] Deploying Veyra to Adobe Premiere Pro CEP directory...
set "TARGET_CEP_DIR=%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer"
if not exist "%APPDATA%\Adobe\CEP\extensions" mkdir "%APPDATA%\Adobe\CEP\extensions" 2>nul
if exist "!TARGET_CEP_DIR!" rmdir /S /Q "!TARGET_CEP_DIR!" 2>nul
mkdir "!TARGET_CEP_DIR!" 2>nul

xcopy /E /I /Y /Q "%SCRIPT_DIR%plugin\*" "!TARGET_CEP_DIR!\" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy extension files.
    pause
    exit /b 1
)

:: Clean legacy extensions to avoid duplicates
if exist "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" rmdir /S /Q "%APPDATA%\Adobe\CEP\extensions\com.voxforge.speechenhancer" 2>nul
if exist "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" rmdir /S /Q "%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer" 2>nul

:: Enable CEP PlayerDebugMode in Windows Registry
for %%v in (7 8 9 10 11 12 13 14 15 16) do (
    reg add "HKCU\Software\Adobe\CSXS.%%v" /v PlayerDebugMode /t REG_SZ /d 1 /f >nul 2>nul
)

:: Write dynamic engine configuration to %CONFIG_DIR% and extension directory
set "ENGINE_SCRIPT=%SCRIPT_DIR%engine\server.py"
powershell -NoProfile -Command "$cfg = @{ python_exe = '!PYTHONW_EXE!'; engine_script = '!ENGINE_SCRIPT!'; project_root = '%SCRIPT_DIR:~0,-1%' }; $json = $cfg | ConvertTo-Json; [System.IO.File]::WriteAllText('!CONFIG_DIR!\engine_config.json', $json, (New-Object System.Text.UTF8Encoding($false))); [System.IO.File]::WriteAllText('!TARGET_CEP_DIR!\engine_config.json', $json, (New-Object System.Text.UTF8Encoding($false)))"
echo [OK] Extension deployed and configured.

:: 8. Verify Engine Starts, /health, and Hardware Detection
echo.
echo [6/6] Verifying Local AI Engine Diagnostics & Live API Health...
if exist "%SCRIPT_DIR%installers\verify_install.py" (
    "!PYTHON_EXE!" "%SCRIPT_DIR%installers\verify_install.py"
) else (
    "!PYTHON_EXE!" -c "import sys; sys.path.insert(0, r'%SCRIPT_DIR:~0,-1%'); from engine.hardware.detector import HardwareDetector; hd = HardwareDetector(); print(f'[OK] Hardware Profile: {hd.get_profile().get(\"tier_name\")}'); from models.manager import ModelManager; mm = ModelManager(); print(f'[OK] Model Registry: {len(mm.registry_data.get(\"models\", {}))} models')"
)
if errorlevel 1 (
    echo [ERROR] Engine self-test verification failed.
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo                      INSTALLATION SUCCESSFUL!
echo ===============================================================================
echo.
echo Veyra is now installed and ready to use in Adobe Premiere Pro.
echo.
echo IMPORTANT: If Adobe Premiere Pro is open, please restart Premiere Pro
echo so it detects the newly installed extension.
echo.
echo TO USE:
echo 1. Open Adobe Premiere Pro.
echo 2. Navigate to: Window -^> Extensions -^> Veyra
echo 3. The engine starts automatically and downloads models on first use.
echo ===============================================================================
echo.

pause
exit /b 0
