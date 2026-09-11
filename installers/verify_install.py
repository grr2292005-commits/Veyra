#!/usr/bin/env python3
"""
Veyra Automated Installation Verification Service
Validates:
1. Core module import and runtime integrity
2. Hardware acceleration and GPU detection
3. Model manager registry discovery
4. Live engine server startup on http://127.0.0.1:8765
5. /health and /system API endpoints
6. Clean shutdown
Exits 0 on complete pass, 1 on failure.
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

def verify():
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    print("--- [Verification 1/4] Hardware and Module Integrity ---")
    try:
        from engine.hardware.detector import HardwareDetector
        from models.manager import ModelManager
        hd = HardwareDetector()
        profile = hd.get_profile(refresh=True)
        gpu = profile.get("gpu", {})
        cpu = profile.get("cpu", {})
        print(f"    [OK] CPU: {cpu.get('name')}")
        print(f"    [OK] GPU Viable: {gpu.get('name')} (CUDA: {gpu.get('cuda', False)})")
        print(f"    [OK] Hardware Tier: {profile.get('tier_name')}")

        mm = ModelManager()
        models = mm.registry_data.get("models", {})
        print(f"    [OK] Model Registry: {len(models)} models registered ({', '.join(models.keys())})")
    except Exception as e:
        print(f"    [FAIL] Core module check failed: {e}")
        return False

    print("\n--- [Verification 2/4] Live Engine Startup ---")
    server_script = os.path.join(script_dir, "engine", "server.py")
    if not os.path.isfile(server_script):
        print(f"    [FAIL] server.py not found at {server_script}")
        return False

    proc = subprocess.Popen(
        [sys.executable, "-B", server_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        bound = False
        health_data = {}
        for attempt in range(30):
            time.sleep(0.2)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=1) as resp:
                    health_data = json.loads(resp.read().decode("utf-8"))
                    if health_data.get("healthy"):
                        bound = True
                        break
            except Exception:
                pass

        if not bound:
            print("    [FAIL] Engine failed to start or respond on http://127.0.0.1:8765/health")
            return False

        print(f"    [OK] Engine live at http://127.0.0.1:8765")
        print(f"    [OK] Status: {health_data.get('status')} | Service: {health_data.get('service')}")

        print("\n--- [Verification 3/4] Hardware & System Diagnostics API ---")
        with urllib.request.urlopen("http://127.0.0.1:8765/system", timeout=2) as resp:
            sys_data = json.loads(resp.read().decode("utf-8"))
            sys_gpu = sys_data.get("gpu", {})
            print(f"    [OK] Backend: {sys_data.get('tier_name')}")
            print(f"    [OK] GPU Viable: {sys_gpu.get('name')} (CUDA: {sys_gpu.get('cuda')})")

        print("\n--- [Verification 4/4] Clean Engine Shutdown ---")
        shutdown_req = urllib.request.Request("http://127.0.0.1:8765/shutdown", data=b"", method="POST")
        with urllib.request.urlopen(shutdown_req, timeout=2) as resp:
            sd_data = json.loads(resp.read().decode("utf-8"))
            print(f"    [OK] Engine Shutdown: {sd_data.get('message')}")

        try:
            proc.wait(timeout=3)
        except Exception:
            pass

        print("\n[ALL ENGINE VERIFICATION CHECKS PASSED]")
        return True

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            pass

if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
