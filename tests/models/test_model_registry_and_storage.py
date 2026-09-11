import os
import sys
import json
import tempfile
import shutil
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from models.storage_manager import ModelStorageManager, FOLDER_ALIASES

class ModelRegistryAndStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_reg_test_")
        self.mm = ModelManager()
        self.original_storage = self.mm.get_storage_path()

    def tearDown(self):
        self.mm.set_storage_path(self.original_storage)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_registry_consistency_across_models(self):
        """Verify registry state, filesystem state, and validation state agree for all models."""
        models = self.mm.list_models()
        self.assertGreaterEqual(len(models), 4)

        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            self.assertIn(mid, models)
            m = models[mid]
            self.assertEqual(m["id"], mid)
            self.assertIn("name", m)
            self.assertIn("status", m)
            if m["installed"]:
                self.assertIsNotNone(m["local_path"])
                self.assertTrue(os.path.isfile(m["local_path"]), f"Reported installed but missing: {m['local_path']}")
                self.assertGreater(m["size_bytes"], 100000)
            else:
                self.assertIn(m["status"], ("missing", "invalid"))

    def test_checkpoint_deleted_externally(self):
        """Deleting a model checkpoint externally must immediately change status to 'missing'."""
        # Create a mock isolated storage
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"
        meta = self.mm.registry_data["models"][mid]
        folder = os.path.join(self.temp_dir, FOLDER_ALIASES[mid][0])
        os.makedirs(folder, exist_ok=True)
        ckpt_path = os.path.join(folder, meta["checkpoint_filename"])

        # Create dummy valid-sized checkpoint
        with open(ckpt_path, "wb") as f:
            f.write(b"0" * 200000)

        # Confirm installed
        self.assertTrue(self.mm.is_installed(mid))
        self.assertEqual(self.mm.list_models()[mid]["status"], "installed")

        # Now delete externally
        os.remove(ckpt_path)

        # Status must immediately be missing / not installed
        self.assertFalse(self.mm.is_installed(mid))
        status, local_path, _ = self.mm.storage_manager.get_model_status(mid)
        self.assertEqual(status, "missing")
        self.assertIsNone(local_path)
        self.assertFalse(self.mm.list_models()[mid]["installed"])

    def test_checkpoint_corrupted_externally(self):
        """A corrupted or zero-length checkpoint must be marked 'invalid', never 'Ready'."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "zipenhancer"
        meta = self.mm.registry_data["models"][mid]
        folder = os.path.join(self.temp_dir, FOLDER_ALIASES[mid][0])
        os.makedirs(folder, exist_ok=True)
        ckpt_path = os.path.join(folder, meta["checkpoint_filename"])

        # Write truncated/empty file (under 100KB threshold)
        with open(ckpt_path, "wb") as f:
            f.write(b"corrupted header")

        status, path, size = self.mm.storage_manager.get_model_status(mid)
        self.assertEqual(status, "invalid")
        self.assertFalse(self.mm.is_installed(mid))

    def test_unknown_model_handling(self):
        """Querying an unknown model ID should return None / safe error, not crash."""
        self.assertIsNone(self.mm.get_model("unknown-neural-model-999"))
        self.assertFalse(self.mm.is_installed("unknown-neural-model-999"))
        self.assertIsNone(self.mm.get_model_file_path("unknown-neural-model-999"))

    def test_duplicate_model_folders_precedence(self):
        """When aliases exist (e.g. MP-SENet vs mp_senet), precedence is deterministic."""
        self.mm.set_storage_path(self.temp_dir)
        mid = "mp_senet"
        meta = self.mm.registry_data["models"][mid]

        folder1 = os.path.join(self.temp_dir, "MP-SENet")
        folder2 = os.path.join(self.temp_dir, "mp_senet")
        os.makedirs(folder1, exist_ok=True)
        os.makedirs(folder2, exist_ok=True)

        ckpt1 = os.path.join(folder1, meta["checkpoint_filename"])
        ckpt2 = os.path.join(folder2, meta["checkpoint_filename"])

        with open(ckpt1, "wb") as f: f.write(b"1" * 200000)
        with open(ckpt2, "wb") as f: f.write(b"2" * 200000)

        # Must resolve to folder1 (first canonical alias)
        resolved = self.mm.get_model_file_path(mid)
        self.assertEqual(os.path.normcase(resolved), os.path.normcase(ckpt1))

if __name__ == "__main__":
    unittest.main()
