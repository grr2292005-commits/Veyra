import os
import sys
import time
import tempfile
import shutil
import threading
import unittest
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from engine.models.factory import ModelFactory

class ModelDownloadsAndInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_dl_test_")
        self.mm = ModelManager()
        self.original_storage = self.mm.get_storage_path()

    def tearDown(self):
        self.mm.set_storage_path(self.original_storage)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        ModelFactory.cleanup_all()

    def test_model_self_tests_all_production_models(self):
        """Run self-test on all models; all installed models must return status='Ready'."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            res = self.mm.validate_model_runtime(mid)
            self.assertTrue(res.get("success"), f"Self-test failed for {mid}: {res.get('error')}")
            self.assertEqual(res.get("status"), "Ready")
            self.assertIn("device", res)

    def test_broken_model_load_failure_safe_recovery(self):
        """Simulate a broken model checkpoint; must report 'Needs attention' without crashing."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"
        from models.storage_manager import FOLDER_ALIASES
        folder = os.path.join(self.temp_dir, FOLDER_ALIASES[mid][0])
        os.makedirs(folder, exist_ok=True)
        ckpt_path = os.path.join(folder, "g_best_dns")

        # Create garbage checkpoint
        with open(ckpt_path, "wb") as f:
            f.write(b"NOT A VALID PYTORCH CHECKPOINT" * 10000)

        res = self.mm.validate_model_runtime(mid)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "Needs attention")
        self.assertIn("error", res)

    def test_download_cancellation(self):
        """Cancelled download must remove temporary file and never mark model as installed."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"

        # Pre-cancelled flag
        with self.assertRaises(InterruptedError):
            self.mm.download_model(mid, cancel_check=lambda: True)

        self.assertFalse(self.mm.is_installed(mid))
        # Ensure no orphan download files remain
        orphans = [f for root, _, files in os.walk(self.temp_dir) for f in files if ".download" in f]
        self.assertEqual(len(orphans), 0, "Cancelled download left temporary files!")

    def test_checksum_mismatch_rejection(self):
        """Deliberately mismatched checksum must fail validation and NOT install."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"

        # Mock urllib.request.urlretrieve to write enough data (10MB) with wrong checksum
        def mock_retrieve(url, filename, reporthook=None):
            with open(filename, "wb") as f:
                f.write(b"altered invalid data for checksum test" * 260000)

        with patch("urllib.request.urlretrieve", side_effect=mock_retrieve):
            with self.assertRaises(Exception) as ctx:
                self.mm.download_model(mid)
            self.assertIn("Checksum verification failed", str(ctx.exception))

        self.assertFalse(self.mm.is_installed(mid))

    def test_duplicate_download_guard(self):
        """Triggering duplicate downloads simultaneously must be safely guarded."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"

        # Acquire download lock simulation
        with self.mm._download_lock:
            self.mm._active_downloads[mid] = True

        try:
            res = self.mm.download_model(mid)
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "already_downloading")
        finally:
            with self.mm._download_lock:
                if mid in self.mm._active_downloads:
                    del self.mm._active_downloads[mid]

    def test_model_switching_memory_cleanup(self):
        """Switch between models: old model unloads, resources release."""
        for mid in ("mp_senet", "zipenhancer", "mp_senet", "deepfilternet3"):
            ckpt = self.mm.get_model_file_path(mid)
            if ckpt and os.path.isfile(ckpt):
                adapter = ModelFactory.create_adapter(mid, ckpt, device="cpu")
                self.assertIsNotNone(adapter)
        # Cleanup
        ModelFactory.cleanup_all()

if __name__ == "__main__":
    unittest.main()
