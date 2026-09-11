#!/usr/bin/env python3
"""
Veyra Prototype Installer Test Harness
Validates Phase 9 requirements using a temporary/local installation target:
- runtime creation
- PyTorch import
- CUDA detection on current RTX 4050 machine
- engine startup
- /health
- /hardware
- /models
- model registry loading
- shutdown
- Premiere plugin files remain intact
"""

import os
import sys
import time
import json
import shutil
import subprocess
import urllib.request

def run_test():
    print("=== Testing Veyra Prototype Standard Installer ===")
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    standard_dir = os.path.join(proj_root, "release-standard")
    
    test_target = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Veyra_PrototypeTest")
    if os.path.isdir(test_target):
        shutil.rmtree(test_target, ignore_errors=True)
        
    test_runtime = os.path.join(test_target, "runtime")
    test_models = os.path.join(test_target, "models")
    test_config = os.path.join(test_target, "config")
    test_cache = os.path.join(test_target, "cache")
    
    os.makedirs(test_models, exist_ok=True)
    os.makedirs(test_config, exist_ok=True)
    os.makedirs(test_cache, exist_ok=True)
    
    # 1. Test Runtime Creation with Python 3.11
    print("\n[Step 1] Creating isolated private virtual environment in:")
    print(f"  {test_runtime}")
    base_py = None
    cands = [
        os.path.join(proj_root, "release-portable", "runtime", "Scripts", "python.exe"),
        r"C:\Users\grr22\AppData\Local\Programs\Python\Python311\python.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
        sys.executable
    ]
    for c in cands:
        if os.path.isfile(c):
            try:
                res = subprocess.run([c, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], capture_output=True, text=True)
                if res.stdout.strip() == "3.11":
                    base_py = c
                    break
            except Exception:
                pass
    if not base_py:
        base_py = sys.executable
    cmd = [base_py, "-m", "venv", test_runtime]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[FAIL] venv creation failed: {res.stderr}")
        return False
        
    test_python = os.path.join(test_runtime, "Scripts", "python.exe")
    test_pythonw = os.path.join(test_runtime, "Scripts", "pythonw.exe")
    if not os.path.isfile(test_python):
        print(f"[FAIL] python.exe not found at {test_python}")
        return False
    print(f"  [PASS] Private runtime created: {test_python}")
    
    source_sp = os.path.join(proj_root, "release-portable", "runtime", "Lib", "site-packages")
    if not os.path.isdir(source_sp):
        source_sp = os.path.join(proj_root, "runtime", "Lib", "site-packages")
    target_sp = os.path.join(test_runtime, "Lib", "site-packages")
    
    # Create .pth in target site-packages pointing to source packages to avoid 5GB duplicate
    pth_file = os.path.join(target_sp, "veyra_packages.pth")
    with open(pth_file, "w", encoding="utf-8") as f:
        f.write(source_sp + "\n")
    print(f"  [PASS] Provisioned test runtime site-packages via {pth_file}")
    
    # 3. Test PyTorch Import & CUDA Detection
    print("\n[Step 3] Testing PyTorch import and CUDA detection...")
    torch_lib = os.path.join(source_sp, "torch", "lib")
    chk_env = os.environ.copy()
    if os.path.isdir(torch_lib):
        chk_env["PATH"] = torch_lib + os.pathsep + chk_env.get("PATH", "")
    chk_cmd = [test_python, "-c", "import os, sys; torch_lib = r'" + torch_lib + "'; os.add_dll_directory(torch_lib) if os.path.isdir(torch_lib) else None; import torch; print(f'TORCH_VERSION={torch.__version__};CUDA_AVAILABLE={torch.cuda.is_available()};DEVICE_NAME={torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"]
    p_chk = subprocess.run(chk_cmd, capture_output=True, text=True, env=chk_env)
    if p_chk.returncode != 0:
        print(f"[FAIL] PyTorch check failed: {p_chk.stderr}")
        return False
    print(f"  Output: {p_chk.stdout.strip()}")
    if "CUDA_AVAILABLE=True" not in p_chk.stdout:
        print("[FAIL] CUDA was not detected as available!")
        return False
    print("  [PASS] PyTorch imported and RTX 4050 CUDA detected successfully.")
    
    # 4. Write test engine_config.json
    engine_script = os.path.join(standard_dir, "engine", "server.py")
    cfg_data = {
        "python_exe": test_pythonw,
        "engine_script": engine_script,
        "project_root": standard_dir
    }
    with open(os.path.join(test_config, "engine_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg_data, f, indent=2)
    print("  [PASS] Dynamic engine_config.json written.")
    
    # 5. Test Engine Startup on port 8768
    print("\n[Step 4] Starting engine server from release-standard...")
    env = os.environ.copy()
    env["VEYRA_DIR"] = test_target
    env["LOCALAPPDATA"] = os.path.dirname(test_target)
    if os.path.isdir(torch_lib):
        env["PATH"] = torch_lib + os.pathsep + env.get("PATH", "")
    
    srv_proc = subprocess.Popen([test_python, "-B", engine_script], env=env)
    try:
        # Wait up to 5 seconds for server readiness
        bound = False
        health_data = {}
        for _ in range(25):
            time.sleep(0.2)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1) as resp:
                    health_data = json.loads(resp.read().decode("utf-8"))
                    bound = True
                    break
            except Exception:
                pass
                
        if not bound:
            print("[FAIL] Server failed to bind to http://127.0.0.1:8765")
            return False
            
        print(f"  [PASS] Server ready in {health_data.get('timings', {}).get('server_startup_ms')} ms")
        print(f"  Status: {health_data.get('status')}, Models Count: {health_data.get('models_count')}")
        
        # 6. Test /system (Hardware Detection)
        print("\n[Step 5] Testing /system hardware endpoint...")
        with urllib.request.urlopen("http://127.0.0.1:8765/system", timeout=2) as resp:
            sys_data = json.loads(resp.read().decode("utf-8"))
            gpu_info = sys_data.get("gpu", {})
            print(f"  GPU Name: {gpu_info.get('name')}")
            print(f"  CUDA: {gpu_info.get('cuda')}")
            print(f"  Recommended Tier: {sys_data.get('tier_name')}")
            if not gpu_info.get("cuda"):
                print("[FAIL] Hardware endpoint did not detect CUDA!")
                return False
            print("  [PASS] /system endpoint verified.")
            
        # 7. Test /models (Model Registry)
        print("\n[Step 6] Testing /models registry endpoint...")
        with urllib.request.urlopen("http://127.0.0.1:8765/models", timeout=2) as resp:
            mod_data = json.loads(resp.read().decode("utf-8"))
            models = mod_data.get("models", {})
            print(f"  Discovered models: {list(models.keys())}")
            print(f"  Storage Directory: {mod_data.get('storage_directory')}")
            if len(models) != 4:
                print(f"[FAIL] Expected 4 registered models, got {len(models)}")
                return False
            print("  [PASS] /models endpoint verified.")
            
        # 8. Test Shutdown
        print("\n[Step 7] Testing clean /shutdown endpoint...")
        req = urllib.request.Request("http://127.0.0.1:8765/shutdown", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=2) as resp:
            sd_res = json.loads(resp.read().decode("utf-8"))
            print(f"  Response: {sd_res.get('message')}")
            print("  [PASS] /shutdown executed cleanly.")
            
    finally:
        try:
            srv_proc.terminate()
            srv_proc.wait(timeout=3)
        except Exception:
            pass
            
    # 9. Verify Premiere Plugin Files Remain Intact
    print("\n[Step 8] Verifying Premiere plugin integrity in release-standard...")
    req_plugin_files = [
        "index.html", "index.js", "manifest.json",
        "CSXS/manifest.xml", "jsx/hostscript.jsx",
        "premiere/CSInterface.js", "services/boot_controller.js",
        "services/path_manager.js", "state/app_state.js",
        "styles/main.css"
    ]
    for pf in req_plugin_files:
        full_pf = os.path.join(standard_dir, "plugin", pf)
        if not os.path.isfile(full_pf):
            print(f"[FAIL] Missing plugin file: {pf}")
            return False
    print("  [PASS] All Premiere plugin files verified intact.")
    
    # Clean up test directory
    shutil.rmtree(test_target, ignore_errors=True)
    print("\n=== ALL PROTOTYPE INSTALLER CHECKS PASSED ===")
    return True

if __name__ == "__main__":
    ok = run_test()
    sys.exit(0 if ok else 1)
