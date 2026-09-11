#!/usr/bin/env python3
"""
Veyra Release Verification Script
Verifies both release architectures:
1. release-standard: Ultralight automated installer package (~1 MB)
2. release-portable: Full offline standalone fallback bundle (~5 GB)
"""

import os
import sys
import re

def verify_portable(release_dir: str) -> bool:
    print(f"\n=== Verifying Veyra Portable Package: {release_dir} ===")
    errors = []
    
    req_dirs = ["plugin", "engine", "models", "runtime", "installers"]
    for d in req_dirs:
        p = os.path.join(release_dir, d)
        if not os.path.isdir(p):
            errors.append(f"Missing required directory: {d}")
        else:
            print(f" [PASS] Directory exists: {d}")

    req_files = ["README.md", "LICENSE", "install.bat", "uninstall.bat", "MANIFEST.txt", "SIZE_REPORT.txt"]
    for f in req_files:
        p = os.path.join(release_dir, f)
        if not os.path.isfile(p):
            errors.append(f"Missing required file: {f}")
        else:
            print(f" [PASS] File exists: {f}")

    req_models = [
        ("deepfilternet3", "model_120.ckpt.best"),
        ("mossformergan", "last_best_checkpoint.pt"),
        ("mp_senet", "g_best_dns"),
        ("zipenhancer", "pytorch_model.bin"),
    ]
    for mid, ckpt in req_models:
        p = os.path.join(release_dir, "models", "storage", mid, ckpt)
        if not os.path.isfile(p):
            errors.append(f"Missing model checkpoint: {mid}/{ckpt}")
        else:
            size_mb = os.path.getsize(p) / (1024 * 1024)
            print(f" [PASS] Model checkpoint verified: {mid}/{ckpt} ({size_mb:.2f} MB)")

    forbidden_patterns = [r"__pycache__", r"\.pytest_cache", r"\.git", r"tests", r"\.debug", r"storage_config\.json", r"\.log$"]
    for root, dirs, files in os.walk(release_dir):
        rel_root = os.path.relpath(root, release_dir)
        if rel_root.startswith("runtime"):
            continue
        for d in dirs:
            for pat in forbidden_patterns:
                if re.search(pat, d, re.IGNORECASE):
                    errors.append(f"Forbidden directory: {os.path.join(rel_root, d)}")
        for f in files:
            for pat in forbidden_patterns:
                if re.search(pat, f, re.IGNORECASE):
                    errors.append(f"Forbidden file: {os.path.join(rel_root, f)}")

    if errors:
        for err in errors:
            print(f"  [ERROR] {err}")
        return False
    print("ALL CHECKS PASSED: Portable bundle is valid.")
    return True

def verify_standard(release_dir: str) -> bool:
    print(f"\n=== Verifying Veyra Standard Package: {release_dir} ===")
    errors = []
    
    # 1. Required Directories (must NOT contain runtime)
    req_dirs = ["plugin", "engine", "models", "installers"]
    for d in req_dirs:
        p = os.path.join(release_dir, d)
        if not os.path.isdir(p):
            errors.append(f"Missing required directory: {d}")
        else:
            print(f" [PASS] Directory exists: {d}")

    if os.path.isdir(os.path.join(release_dir, "runtime")):
        errors.append("Standard release must NOT bundle runtime directory!")

    # 2. Required Files
    req_files = ["README.md", "LICENSE", "install.bat", "uninstall.bat", "requirements-standard.txt"]
    for f in req_files:
        p = os.path.join(release_dir, f)
        if not os.path.isfile(p):
            errors.append(f"Missing required file: {f}")
        else:
            print(f" [PASS] File exists: {f}")

    # 3. Required Models Code
    req_model_files = ["manager.py", "registry.json", "storage_manager.py"]
    for mf in req_model_files:
        p = os.path.join(release_dir, "models", mf)
        if not os.path.isfile(p):
            errors.append(f"Missing model code file: {mf}")
        else:
            print(f" [PASS] Model code verified: {mf}")

    # 4. Check that heavy checkpoints are NOT bundled in standard release
    storage_dir = os.path.join(release_dir, "models", "storage")
    if os.path.isdir(storage_dir):
        files_in_storage = [f for f in os.listdir(storage_dir) if not f.startswith(".")]
        if files_in_storage:
            errors.append(f"Standard release should not bundle checkpoints in models/storage: {files_in_storage}")

    # 5. Check for Forbidden Dev Files and hardcoded paths
    forbidden_patterns = [r"__pycache__", r"\.pytest_cache", r"\.git", r"tests", r"\.debug", r"storage_config\.json", r"\.log$"]
    dev_path_patterns = [re.compile(r"C:\\Users\\grr22", re.IGNORECASE), re.compile(r"Desktop\\audio test", re.IGNORECASE)]
    scan_exts = {".html", ".js", ".jsx", ".json", ".xml", ".bat", ".py", ".md", ".txt", ".css"}
    
    for root, dirs, files in os.walk(release_dir):
        rel_root = os.path.relpath(root, release_dir)
        for d in dirs:
            for pat in forbidden_patterns:
                if re.search(pat, d, re.IGNORECASE):
                    errors.append(f"Forbidden directory: {os.path.join(rel_root, d)}")
        for f in files:
            for pat in forbidden_patterns:
                if re.search(pat, f, re.IGNORECASE):
                    errors.append(f"Forbidden file: {os.path.join(rel_root, f)}")
            ext = os.path.splitext(f)[1].lower()
            if ext in scan_exts:
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                        for line_no, line in enumerate(fp, 1):
                            for pat in dev_path_patterns:
                                if pat.search(line):
                                    errors.append(f"Hardcoded dev path in {os.path.join(rel_root, f)}:{line_no}: {line.strip()[:80]}")
                except Exception as ex:
                    pass

    # Total size check
    total_sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(release_dir) for f in fs)
    size_mb = total_sz / (1024 * 1024)
    print(f" [PASS] Total standard release size: {size_mb:.2f} MB ({total_sz:,} bytes)")
    if size_mb > 10.0:
        errors.append(f"Standard release size ({size_mb:.2f} MB) exceeds 10 MB limit!")

    if errors:
        for err in errors:
            print(f"  [ERROR] {err}")
        return False
    print("ALL CHECKS PASSED: Standard release is ultralight, clean, and valid.")
    return True

if __name__ == "__main__":
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    portable_dir = os.path.join(proj_root, "release-portable")
    standard_dir = os.path.join(proj_root, "release-standard")
    
    ok_p = verify_portable(portable_dir) if os.path.isdir(portable_dir) else True
    ok_s = verify_standard(standard_dir) if os.path.isdir(standard_dir) else True
    
    if ok_p and ok_s:
        print("\n========================================")
        print("ALL RELEASE TARGETS VERIFIED SUCCESSFULLY!")
        print("========================================")
        sys.exit(0)
    else:
        print("\n[FAIL] Release verification failed.")
        sys.exit(1)
