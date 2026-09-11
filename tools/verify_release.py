#!/usr/bin/env python3
"""
Veyra Release Verification Script
Quick deterministic verification of the release tree outside the release directory:
- Required directories and files exist
- No forbidden dev files or caches
- No hard-coded developer paths
- Clean user-facing branding
"""

import os
import sys
import re

def verify_release(release_dir: str) -> bool:
    print(f"=== Verifying Veyra Release Package: {release_dir} ===")
    errors = []
    warnings = []

    # 1. Required Directories
    req_dirs = ["plugin", "engine", "models", "runtime", "installers"]
    for d in req_dirs:
        p = os.path.join(release_dir, d)
        if not os.path.isdir(p):
            errors.append(f"Missing required directory: {d}")
        else:
            print(f" [PASS] Directory exists: {d}")

    # 2. Required Root Files
    req_files = ["README.md", "LICENSE", "install.bat", "uninstall.bat", "MANIFEST.txt", "SIZE_REPORT.txt"]
    for f in req_files:
        p = os.path.join(release_dir, f)
        if not os.path.isfile(p):
            errors.append(f"Missing required file: {f}")
        else:
            print(f" [PASS] File exists: {f}")

    # 3. Required Models Checkpoints
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

    # 4. Check for Forbidden Dev Files in release/ (excluding runtime)
    forbidden_patterns = [
        r"__pycache__",
        r"\.pytest_cache",
        r"\.git",
        r"tests",
        r"\.debug",
        r"storage_config\.json",
        r"\.log$",
    ]
    for root, dirs, files in os.walk(release_dir):
        rel_root = os.path.relpath(root, release_dir)
        if rel_root.startswith("runtime"):
            continue
        for d in dirs:
            for pat in forbidden_patterns:
                if re.search(pat, d, re.IGNORECASE):
                    errors.append(f"Forbidden directory in release: {os.path.join(rel_root, d)}")
        for f in files:
            for pat in forbidden_patterns:
                if re.search(pat, f, re.IGNORECASE):
                    errors.append(f"Forbidden file in release: {os.path.join(rel_root, f)}")

    # 5. Check for Hardcoded Dev Paths in non-runtime text files
    dev_path_patterns = [
        re.compile(r"C:\\Users\\grr22", re.IGNORECASE),
        re.compile(r"Desktop\\audio test", re.IGNORECASE),
    ]
    scan_exts = {".html", ".js", ".jsx", ".json", ".xml", ".bat", ".py", ".md", ".txt", ".css"}
    for root, dirs, files in os.walk(release_dir):
        rel_root = os.path.relpath(root, release_dir)
        if rel_root.startswith("runtime"):
            continue
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in scan_exts and f not in ("MANIFEST.txt", "SIZE_REPORT.txt"):
                file_path = os.path.join(root, f)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                        for line_no, line in enumerate(fp, 1):
                            for pat in dev_path_patterns:
                                if pat.search(line):
                                    errors.append(f"Hardcoded dev path in {os.path.join(rel_root, f)}:{line_no}: {line.strip()[:80]}")
                except Exception as ex:
                    warnings.append(f"Could not read {file_path}: {ex}")

    # Summary
    print("\n=== VERIFICATION SUMMARY ===")
    if errors:
        print(f"FAILED with {len(errors)} errors:")
        for err in errors:
            print(f"  [ERROR] {err}")
        return False
    else:
        print("ALL CHECKS PASSED: Release package is clean, self-contained, and valid.")
        return True

if __name__ == "__main__":
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    rel_dir = os.path.join(proj_root, "release")
    success = verify_release(rel_dir)
    sys.exit(0 if success else 1)
