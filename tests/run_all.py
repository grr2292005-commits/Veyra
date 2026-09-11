import os
import sys
import time
import json
import traceback
import unittest
from typing import Dict, Any, List

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure execution in Speechify private runtime if available
runtime_python = os.path.join(PROJECT_ROOT, "runtime", "Scripts", "python.exe")
if os.path.isfile(runtime_python) and os.path.normcase(sys.executable) != os.path.normcase(runtime_python):
    import subprocess
    cmd = [runtime_python, "-m", "tests.run_all"] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))

from engine.core.health import runProductionHealthCheck

# Subsystem and severity mapping
SUITE_REGISTRY = [
    ("tests.filesystem.test_storage_configuration", "filesystem", "CRITICAL"),
    ("tests.models.test_model_registry_and_storage", "models", "CRITICAL"),
    ("tests.models.test_model_downloads_and_install", "models", "HIGH"),
    ("tests.runtime.test_runtime_dependencies", "runtime", "CRITICAL"),
    ("tests.hardware.test_hardware_detection", "hardware", "HIGH"),
    ("tests.hardware.test_hardware_ui_propagation", "hardware", "HIGH"),
    ("tests.audio.test_audio_pipeline_and_naming", "audio", "CRITICAL"),
    ("tests.lifecycle.test_engine_lifecycle", "lifecycle", "CRITICAL"),
    ("tests.failure.test_failure_recovery", "failure", "HIGH"),
    ("tests.stress.test_resource_leaks", "stress", "MEDIUM"),
    ("tests.unit.test_track_selection", "unit", "MEDIUM"),
    ("tests.unit.test_security_and_paths", "unit", "HIGH"),
    ("tests.unit.test_context_serialization", "unit", "CRITICAL"),
    ("tests.unit.test_multi_track_processing", "unit", "CRITICAL"),
    ("tests.unit.test_timeline_placement", "unit", "CRITICAL"),
    ("tests.unit.test_final_pipeline_rebuild", "unit", "CRITICAL"),
    ("tests.unit.test_clip_based_range_processing", "unit", "CRITICAL"),
    ("tests.integration.test_stale_source_prevention", "integration", "CRITICAL"),
    ("tests.integration.test_full_system_integration", "integration", "CRITICAL"),
]

def run_all_tests():
    print("=" * 80)
    print("        SPEECHIFY PRODUCTION HARDENING & AUTOMATED TECHNICAL QA")
    print("=" * 80)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python:    {sys.executable}")
    print(f"Root:      {PROJECT_ROOT}")
    print("-" * 80)

    loader = unittest.TestLoader()
    test_records: List[Dict[str, Any]] = []

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    critical_failed = 0
    high_failed = 0
    medium_failed = 0
    low_failed = 0

    suite_start_time = time.perf_counter()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    for module_name, subsystem, severity in SUITE_REGISTRY:
        try:
            mod = __import__(module_name, fromlist=["*"])
            suite = loader.loadTestsFromModule(mod)
        except Exception as ex:
            err_msg = f"Failed importing {module_name}: {ex}\n{traceback.format_exc()}"
            print(f"[-] ERROR IMPORTING {module_name}: {ex}")
            test_records.append({
                "name": module_name,
                "subsystem": subsystem,
                "severity": severity,
                "status": "FAIL",
                "duration_ms": 0.0,
                "error": err_msg
            })
            total_failed += 1
            if severity == "CRITICAL": critical_failed += 1
            elif severity == "HIGH": high_failed += 1
            continue

        for test in _flatten_suite(suite):
            test_id = test.id()
            test_name = test_id.split(".")[-1]
            t0 = time.perf_counter()
            result = unittest.TestResult()

            try:
                test.run(result)
            except Exception as e:
                result.addError(test, sys.exc_info())

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            if result.wasSuccessful():
                status = "PASS"
                error = None
                total_passed += 1
                symbol = "+"
            elif result.skipped:
                status = "SKIPPED"
                error = result.skipped[0][1] if result.skipped else "Skipped"
                total_skipped += 1
                symbol = "o"
            else:
                status = "FAIL"
                total_failed += 1
                symbol = "X"
                if severity == "CRITICAL": critical_failed += 1
                elif severity == "HIGH": high_failed += 1
                elif severity == "MEDIUM": medium_failed += 1
                else: low_failed += 1

                err_lines = []
                for _, err_str in result.failures + result.errors:
                    err_lines.append(err_str)
                error = "\n".join(err_lines)

            test_records.append({
                "test_name": test_name,
                "test_id": test_id,
                "subsystem": subsystem,
                "severity": severity,
                "status": status,
                "duration_ms": elapsed_ms,
                "error": error
            })

            # Real-time console reporting
            status_tag = f"[{status}]"
            print(f" {symbol} {status_tag:<8} {subsystem:<12} {severity:<9} {test_name:<40} ({elapsed_ms} ms)")
            if error:
                print(f"      └─ Error: {error.strip().splitlines()[-1]}")

    total_duration_sec = round(time.perf_counter() - suite_start_time, 2)

    # Compile machine-readable results.json
    results_json_data = {
        "summary": {
            "total": len(test_records),
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "duration_sec": total_duration_sec,
            "critical_failed": critical_failed,
            "high_failed": high_failed,
            "medium_failed": medium_failed,
            "low_failed": low_failed
        },
        "tests": test_records
    }

    results_path = os.path.join(PROJECT_ROOT, "tests", "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_json_data, f, indent=2)

    # Run Technical Health Check
    health_path = os.path.join(PROJECT_ROOT, "tests", "health_report.json")
    health_data = runProductionHealthCheck(save_path=health_path)

    # Print Summary Table
    print("\n" + "=" * 80)
    print("                             QA SUITE SUMMARY")
    print("=" * 80)
    print(f" Total Tests Run:   {len(test_records)}")
    print(f" Passed:            {total_passed}")
    print(f" Failed:            {total_failed}")
    print(f" Skipped:           {total_skipped}")
    print(f" Critical Failed:   {critical_failed}")
    print(f" High Failed:       {high_failed}")
    print(f" Medium Failed:     {medium_failed}")
    print(f" Low Failed:        {low_failed}")
    print(f" Suite Duration:    {total_duration_sec} s")
    print(f" Results File:      {results_path}")
    print(f" Health Report:     {health_path}")
    print("-" * 80)

    # Production Readiness Classification (Section 198)
    if critical_failed > 0:
        readiness = "NOT READY (CRITICAL FAILURES)"
    elif high_failed > 0:
        readiness = "NEEDS FIXES (HIGH FAILURES)"
    elif total_failed > 0:
        readiness = "TECHNICALLY STABLE (MINOR FAILURES)"
    else:
        readiness = "PRODUCTION CANDIDATE"

    print(f" Production Readiness: {readiness}")
    print("=" * 80 + "\n")

    # Return non-zero exit code if critical tests fail (Section 4)
    if critical_failed > 0 or high_failed > 0:
        sys.exit(1)
    return 0

def _flatten_suite(suite):
    """Recursively yields individual TestCase instances from a TestSuite."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten_suite(item)
        else:
            yield item

if __name__ == "__main__":
    run_all_tests()
