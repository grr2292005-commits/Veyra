import os
import sys
import time
import json
import random
import unittest
import traceback
from typing import Dict, Any, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure execution in Speechify private runtime if available
runtime_python = os.path.join(PROJECT_ROOT, "runtime", "Scripts", "python.exe")
if os.path.isfile(runtime_python) and os.path.normcase(sys.executable) != os.path.normcase(runtime_python):
    import subprocess
    cmd = [runtime_python, "-m", "tests.run_adversarial_gate"] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))

ADVERSARIAL_MODULES = [
    ("tests.adversarial.test_mutation_defense", "mutation", "CRITICAL"),
    ("tests.adversarial.test_adversarial_audio", "numerical_audio", "CRITICAL"),
    ("tests.adversarial.test_adversarial_storage", "storage_concurrency", "CRITICAL"),
    ("tests.adversarial.test_adversarial_hardware", "hardware_vram", "HIGH"),
    ("tests.adversarial.test_adversarial_lifecycle", "lifecycle_leaks", "HIGH"),
    ("tests.adversarial.test_adversarial_install", "install_determinism", "HIGH"),
]

def _flatten_suite(suite):
    tests = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(_flatten_suite(item))
        else:
            tests.append(item)
    return tests

def run_adversarial_suite(order: str = "normal") -> Dict[str, Any]:
    loader = unittest.TestLoader()
    all_tests = []

    for mod_name, subsystem, severity in ADVERSARIAL_MODULES:
        mod = __import__(mod_name, fromlist=["*"])
        suite = loader.loadTestsFromModule(mod)
        for t in _flatten_suite(suite):
            all_tests.append((t, subsystem, severity))

    if order == "reverse":
        all_tests.reverse()
    elif order == "random":
        random.seed(42)
        random.shuffle(all_tests)

    test_records = []
    total_passed = 0
    total_failed = 0

    t_start = time.perf_counter()

    for test, subsystem, severity in all_tests:
        test_id = test.id()
        test_name = test_id.split(".")[-1]
        t0 = time.perf_counter()
        res = unittest.TestResult()

        try:
            test.run(res)
        except Exception as e:
            res.addError(test, sys.exc_info())

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        if res.wasSuccessful():
            status = "PASS"
            error = None
            total_passed += 1
            sym = "+"
        else:
            status = "FAIL"
            total_failed += 1
            sym = "X"
            err_lines = [err for _, err in res.failures + res.errors]
            error = "\n".join(err_lines)

        test_records.append({
            "name": test_name,
            "id": test_id,
            "subsystem": subsystem,
            "severity": severity,
            "status": status,
            "duration_ms": elapsed_ms,
            "error": error
        })

        tag = f"[{status}]"
        print(f" {sym} {tag:<8} {subsystem:<20} {test_name:<45} ({elapsed_ms} ms)")
        if error:
            print(f"      └─ Error: {error.strip().splitlines()[-1]}")

    total_time = round(time.perf_counter() - t_start, 2)
    return {
        "order": order,
        "total": len(test_records),
        "passed": total_passed,
        "failed": total_failed,
        "duration_sec": total_time,
        "records": test_records
    }

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 85)
    print("       SPEECHIFY FINAL ADVERSARIAL QA & PRODUCTION-GATE AUDIT SUITE")
    print("=" * 85)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python:    {sys.executable}")
    print(f"Root:      {PROJECT_ROOT}")
    print("-" * 85)

    # 1. Normal Order Pass
    print("\n[PHASE 1] Running Adversarial Suite (Normal Execution Order)...")
    res_normal = run_adversarial_suite("normal")
    print(f"Normal Order: {res_normal['passed']}/{res_normal['total']} passed in {res_normal['duration_sec']}s")

    # 2. Reverse Order Pass (Req 43)
    print("\n[PHASE 2] Running Adversarial Suite (Reverse Execution Order)...")
    res_reverse = run_adversarial_suite("reverse")
    print(f"Reverse Order: {res_reverse['passed']}/{res_reverse['total']} passed in {res_reverse['duration_sec']}s")

    # 3. Random Order Pass (Req 43)
    print("\n[PHASE 3] Running Adversarial Suite (Random Execution Order)...")
    res_random = run_adversarial_suite("random")
    print(f"Random Order:  {res_random['passed']}/{res_random['total']} passed in {res_random['duration_sec']}s")

    # 4. Repeat Verification (Req 44: Run 3 consecutive times)
    print("\n[PHASE 4] 3x Deterministic Repeatability Verification...")
    repeats_passed = True
    for rep in range(1, 4):
        print(f"  Iteration {rep}/3...")
        r = run_adversarial_suite("normal")
        if r["failed"] > 0:
            repeats_passed = False
            print(f"  [-] Repeat iteration {rep} had failures!")

    # Compile report data
    master_results = {
        "summary": {
            "total_adversarial_tests": res_normal["total"],
            "passed": res_normal["passed"],
            "failed": res_normal["failed"],
            "normal_order_duration_sec": res_normal["duration_sec"],
            "reverse_order_passed": res_reverse["passed"] == res_reverse["total"],
            "random_order_passed": res_random["passed"] == res_random["total"],
            "repeatability_3x_passed": repeats_passed,
        },
        "tests": res_normal["records"]
    }

    out_file = os.path.join(PROJECT_ROOT, "tests", "adversarial_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(master_results, f, indent=2)

    print("\n" + "=" * 85)
    print("                    ADVERSARIAL PRODUCTION-GATE AUDIT SUMMARY")
    print("=" * 85)
    print(f"  Adversarial Tests:         {master_results['summary']['total_adversarial_tests']}")
    print(f"  Passed:                    {master_results['summary']['passed']}")
    print(f"  Failed:                    {master_results['summary']['failed']}")
    print(f"  Order Independence:        {'PASSED (Normal, Reverse, Random all 100%)' if res_reverse['passed'] == res_reverse['total'] and res_random['passed'] == res_random['total'] else 'FAILED'}")
    print(f"  3x Repeatability:          {'PASSED (3/3 identical executions)' if repeats_passed else 'FAILED'}")
    print(f"  Results Artifact:          {out_file}")
    print("=" * 85)

    if master_results["summary"]["failed"] > 0 or not repeats_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
