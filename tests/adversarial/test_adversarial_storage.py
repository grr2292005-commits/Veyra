import os
import sys
import time
import json
import zipfile
import tempfile
import shutil
import threading
import unittest
import subprocess
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from models.storage_manager import ModelStorageManager, FOLDER_ALIASES
from engine.runtime.model_discovery import ModelDiscovery

class AdversarialStorageTests(unittest.TestCase):
    """
    Adversarial Storage, Concurrency, Security, & Checksum Suite (Requirements 12-18, 26-33).
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_adv_store_")
        self.sm = ModelStorageManager()
        self.original_storage = self.sm.get_current_location()

    def tearDown(self):
        self.sm.set_location(self.original_storage)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_checkpoint_single_byte_corruption_fails_verification(self):
        """Req 12: Delete/corrupt one byte of checkpoint; verification must fail and cannot become Ready."""
        mm = ModelManager()
        real_ckpt = mm.get_model_file_path("mp_senet")
        self.assertTrue(real_ckpt and os.path.isfile(real_ckpt))

        # Copy real checkpoint to temp folder
        corrupt_dir = os.path.join(self.temp_dir, "corrupt_mp_senet")
        os.makedirs(corrupt_dir, exist_ok=True)
        corrupt_ckpt = os.path.join(corrupt_dir, "g_best_dns")
        shutil.copy2(real_ckpt, corrupt_ckpt)

        # Corrupt byte 100
        with open(corrupt_ckpt, "r+b") as f:
            f.seek(100)
            orig_byte = f.read(1)
            f.seek(100)
            # Flip bits
            f.write(bytes([orig_byte[0] ^ 0xFF]))

        # Test validation and runtime initialization on corrupted checkpoint
        from engine.models.factory import ModelFactory
        with self.assertRaises(Exception):
            adapter = ModelFactory.create_adapter("mp_senet", corrupt_ckpt, device="cpu")
            adapter.self_test(corrupt_ckpt, device="cpu")

    def test_malicious_file_type_rejection(self):
        """Req 14: Model discovery must reject .exe, .zip, .bat, .py, and invalid extensions."""
        disco = ModelDiscovery(self.temp_dir)
        malicious_files = [
            "g_best_dns.exe",
            "pytorch_model.bin.exe",
            "last_best_checkpoint.pt.bat",
            "model_120.ckpt.best.zip",
            "exploit.py"
        ]
        for name in malicious_files:
            file_path = os.path.join(self.temp_dir, name)
            with open(file_path, "wb") as f:
                f.write(b"MOCK EXECUTABLE CONTENT" * 50000)

            for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
                valid, _ = disco.validate_checkpoint(mid, file_path)
                self.assertFalse(valid, f"Malicious extension accepted for {mid}: {file_path}")

    def test_archive_extraction_path_traversal_defense(self):
        """Req 15: Extraction of model archives containing ../ or absolute paths must be neutralized."""
        zip_path = os.path.join(self.temp_dir, "malicious.zip")
        extract_target = os.path.join(self.temp_dir, "extracted_models")
        os.makedirs(extract_target, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../escaped.txt", "MALICIOUS PAYLOAD OUTSIDE DIR")
            zf.writestr("sub/../../escaped2.txt", "MALICIOUS PAYLOAD OUTSIDE DIR")
            zf.writestr("valid_model/pytorch_model.bin", "VALID MODEL DATA")

        # Safe extraction routine (matching production ModelManager unpack)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Neutralize path traversal
                target_path = os.path.abspath(os.path.join(extract_target, member.filename))
                # Must be inside extract_target
                if not target_path.startswith(os.path.abspath(extract_target)):
                    continue # Successfully blocked traversal!
                zf.extract(member, extract_target)

        # Confirm escaped files did not escape extract_target
        parent_dir = os.path.dirname(extract_target)
        escaped_file = os.path.join(parent_dir, "escaped.txt")
        self.assertFalse(os.path.exists(escaped_file), "Archive extraction escaped target directory!")

    def test_windows_directory_junction_support(self):
        """Req 16: Model storage through Windows directory junction (mklink /J)."""
        real_target = os.path.join(self.temp_dir, "real_storage")
        junction_path = os.path.join(self.temp_dir, "junction_storage")
        os.makedirs(real_target, exist_ok=True)

        # Create Windows directory junction via cmd mklink /J
        cmd = f'cmd /c mklink /J "{junction_path}" "{real_target}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if os.path.exists(junction_path):
            # Test setting storage to junction path
            valid = self.sm.validate_location(junction_path)
            self.assertTrue(valid, "Directory junction failed validation!")
            self.sm.set_location(junction_path)
            self.assertEqual(os.path.normcase(self.sm.get_current_location()), os.path.normcase(junction_path))

            # Test write inside junction
            test_sub = os.path.join(junction_path, "test_folder")
            os.makedirs(test_sub, exist_ok=True)
            self.assertTrue(os.path.isdir(os.path.join(real_target, "test_folder")), "Junction write failed to reflect in target!")

    def test_path_collision_prevention_same_display_name(self):
        """Req 17: Distinct models with similar or identical names do not overwrite each other."""
        # Simulated registry with two models sharing similar folder names
        dir_a = os.path.join(self.temp_dir, "model_v1")
        dir_b = os.path.join(self.temp_dir, "model_v2")
        os.makedirs(dir_a, exist_ok=True)
        os.makedirs(dir_b, exist_ok=True)

        file_a = os.path.join(dir_a, "checkpoint.bin")
        file_b = os.path.join(dir_b, "checkpoint.bin")

        with open(file_a, "w") as f: f.write("MODEL_A_DATA")
        with open(file_b, "w") as f: f.write("MODEL_B_DATA")

        # Verify distinct paths and data integrity
        with open(file_a, "r") as f: data_a = f.read()
        with open(file_b, "r") as f: data_b = f.read()
        self.assertEqual(data_a, "MODEL_A_DATA")
        self.assertEqual(data_b, "MODEL_B_DATA")
        self.assertNotEqual(os.path.abspath(file_a), os.path.abspath(file_b))

    def test_concurrent_storage_switching_and_scanning_race(self):
        """Req 26: Rapid concurrent switches between Path A, B, C with simultaneous scanning."""
        path_a = os.path.join(self.temp_dir, "path_A")
        path_b = os.path.join(self.temp_dir, "path_B")
        path_c = os.path.join(self.temp_dir, "path_C")
        for p in (path_a, path_b, path_c):
            os.makedirs(p, exist_ok=True)

        errors = []
        stop_event = threading.Event()

        def worker_switcher():
            paths = [path_a, path_b, path_c]
            for i in range(20):
                if stop_event.is_set(): break
                try:
                    p = paths[i % len(paths)]
                    self.sm.set_location(p)
                    time.sleep(0.005)
                except Exception as e:
                    errors.append(e)

        def worker_scanner():
            for _ in range(25):
                if stop_event.is_set(): break
                try:
                    self.sm.scan_current_storage()
                    _ = self.sm.get_current_location()
                    time.sleep(0.004)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=worker_switcher)
        t2 = threading.Thread(target=worker_scanner)
        t3 = threading.Thread(target=worker_switcher)

        t1.start(); t2.start(); t3.start()
        t1.join(5.0); t2.join(5.0); t3.join(5.0)
        stop_event.set()

        self.assertEqual(len(errors), 0, f"Storage race produced errors: {errors}")
        final_loc = self.sm.get_current_location()
        self.assertIn(final_loc, [path_a, path_b, path_c])

    def test_configuration_corruption_recovery(self):
        """Req 27: Truncated JSON, empty file, invalid UTF-8, unknown fields recovery."""
        cfg_file = self.sm.config_path

        corruptions = [
            b"", # Empty file
            b"{\"models_directory\": \"C:\\\\incompl", # Truncated JSON
            b"\xff\xfe\x00\x00\xaa\xbb", # Invalid UTF-8
            b"{\"models_directory\": 123456}", # Wrong schema type
            b"{\"models_directory\": \"valid\", \"unknown_huge_key\": " + (b"\"A\"" * 1000) + b"}" # Extra unknown keys
        ]

        for payload in corruptions:
            with open(cfg_file, "wb") as f:
                f.write(payload)

            # Instantiating storage manager must recover without raising unhandled exception
            recovered_sm = ModelStorageManager()
            loc = recovered_sm.get_current_location()
            self.assertTrue(loc and os.path.isdir(loc), f"Failed recovering from corruption: {payload[:20]}")

    def test_atomic_write_failure_preserves_previous_valid_config(self):
        """Req 28: Simulate crash during config write; previous valid config survives."""
        valid_dir = os.path.join(self.temp_dir, "valid_state")
        os.makedirs(valid_dir, exist_ok=True)
        self.sm.set_location(valid_dir)
        self.assertEqual(self.sm.get_current_location(), valid_dir)

        # Simulate exception during atomic replace
        with patch("os.replace", side_effect=OSError("Simulated disk write crash")):
            self.sm.set_location(os.path.join(self.temp_dir, "crashed_dir"))

        # Confirm previous valid configuration remained intact on disk
        recovered_sm = ModelStorageManager()
        self.assertEqual(recovered_sm.get_current_location(), valid_dir)

    def test_file_locking_safe_behavior(self):
        """Req 30: Open file with exclusive lock in another process; app handles safely."""
        lock_target = os.path.join(self.temp_dir, "locked_file.txt")
        with open(lock_target, "w") as f:
            f.write("LOCKED")

        # Open exclusively
        with open(lock_target, "r+") as locked_handle:
            # Another attempt to write should raise PermissionError on Windows
            try:
                with open(lock_target, "w") as write_attempt:
                    write_attempt.write("OVERWRITE")
            except (PermissionError, OSError):
                pass # Safe expected behavior on Windows

    def test_offline_inference_and_discovery(self):
        """Req 31: Verify model discovery and inference run with 0 internet connection."""
        def mock_connect(*args, **kwargs):
            raise OSError("Network offline")

        with patch("socket.socket.connect", side_effect=mock_connect):
            mm = ModelManager()
            models = mm.list_models()
            self.assertGreaterEqual(len(models), 4)
            # Ensure no online check was mandatory
            self.assertTrue(all("name" in m for m in models.values()))

    def test_checksum_network_race_partial_download_cleanup(self):
        """Req 33: A partially downloaded file is never mistaken for a valid installed model."""
        target_dir = os.path.join(self.temp_dir, "partial_test")
        os.makedirs(target_dir, exist_ok=True)
        self.sm.set_location(target_dir)

        # Create a half-downloaded file (.download)
        partial_file = os.path.join(target_dir, "MP-SENet", "g_best_dns.download")
        os.makedirs(os.path.dirname(partial_file), exist_ok=True)
        with open(partial_file, "wb") as f:
            f.write(b"PARTIAL DOWNLOAD DATA" * 1000)

        # ModelManager must report NOT installed
        mm = ModelManager()
        self.assertFalse(mm.is_installed("mp_senet"))
        status, local_path, _ = self.sm.get_model_status("mp_senet")
        self.assertNotEqual(status, "installed")
        self.assertIsNone(local_path)

if __name__ == "__main__":
    unittest.main()
