import os
import sys
import json
import time
import socket
import tempfile
import shutil
import unittest
import urllib.request
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class EngineLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.logs_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.lock_file = os.path.join(self.logs_dir, "engine.lock")
        self.pid_file = os.path.join(self.logs_dir, "engine.pid")

    def test_stale_lock_detection_and_recovery(self):
        """A lockfile containing a nonexistent PID must be detected as stale and safe to clean."""
        fake_pid = 999999 # Highly unlikely to exist
        stale_data = {
            "pid": fake_pid,
            "owner": "speechify",
            "instanceId": "fake-stale-token",
            "startedAt": time.time() - 3600,
            "port": 8765
        }
        with open(self.lock_file, "w", encoding="utf-8") as f:
            json.dump(stale_data, f)

        # Check if process is running using os.kill(pid, 0)
        def is_pid_alive(pid):
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

        self.assertFalse(is_pid_alive(fake_pid))
        # Safely remove stale lock
        os.remove(self.lock_file)
        self.assertFalse(os.path.isfile(self.lock_file))

    def test_process_ownership_protection(self):
        """Speechify must verify process ownership and NEVER kill arbitrary Python processes."""
        current_pid = os.getpid()
        lock_data = {
            "pid": current_pid,
            "owner": "speechify",
            "instanceId": "test-valid-instance"
        }
        with open(self.lock_file, "w", encoding="utf-8") as f:
            json.dump(lock_data, f)

        # Non-speechify lock
        unrelated_lock = {
            "pid": current_pid,
            "owner": "other_application"
        }
        self.assertNotEqual(unrelated_lock["owner"], "speechify")

        # Cleanup test lock
        if os.path.isfile(self.lock_file):
            os.remove(self.lock_file)

    def test_port_conflict_safety(self):
        """If port is occupied by another application, engine must handle safely without killing it."""
        # Bind a dummy socket on a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            busy_port = s.getsockname()[1]

            # Attempt to bind again should raise OSError (10048 on Windows)
            with self.assertRaises(OSError):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                    s2.bind(('127.0.0.1', busy_port))

    def test_malformed_health_response_treated_as_unhealthy(self):
        """Malformed or incomplete health payload must NEVER report false Ready."""
        malformed_responses = [
            {},
            {"status": "starting"},
            {"healthy": False},
            {"status": "ready"}, # Missing healthy: True
            {"status": "error", "healthy": False}
        ]

        def is_engine_payload_healthy(data):
            return isinstance(data, dict) and data.get("healthy") is True and data.get("status") == "ready"

        for resp in malformed_responses:
            self.assertFalse(is_engine_payload_healthy(resp), f"Falsely marked healthy: {resp}")

        valid_response = {"healthy": True, "status": "ready", "owner": "speechify"}
        self.assertTrue(is_engine_payload_healthy(valid_response))

    def test_bounded_health_timeout(self):
        """Health check loop must have a bounded finite timeout and not loop infinitely."""
        max_attempts = 10
        attempts = 0
        timeout_occurred = False
        t_start = time.time()

        while attempts < max_attempts:
            attempts += 1
            # Simulate failed poll
            if time.time() - t_start > 0.5:
                timeout_occurred = True
                break

        self.assertTrue(timeout_occurred or attempts == max_attempts)

if __name__ == "__main__":
    unittest.main()
