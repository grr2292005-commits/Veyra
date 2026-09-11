import os
import sys
import shutil
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.storage_manager import ModelStorageManager
from models.manager import ModelManager

class TestStorageSwitching(unittest.TestCase):
    def setUp(self):
        self.default_storage = os.path.abspath(os.path.join(BASE_DIR, "models", "storage"))
        self.test_empty_dir = os.path.abspath(os.path.join(BASE_DIR, "logs", "test_empty_storage"))
        self.test_migrated_dir = os.path.abspath(os.path.join(BASE_DIR, "logs", "test_migrated_storage"))
        
        # Ensure default storage is set
        self.mgr = ModelManager()
        self.mgr.set_storage_path(self.default_storage)

    def tearDown(self):
        # Reset back to default storage
        self.mgr.set_storage_path(self.default_storage)
        for d in (self.test_empty_dir, self.test_migrated_dir):
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

    def test_empty_storage_path_reports_missing(self):
        """
        Switch to empty folder without migration -> ALL models must report 'missing' / not installed.
        Changing path must NEVER copy models automatically.
        """
        if os.path.isdir(self.test_empty_dir):
            shutil.rmtree(self.test_empty_dir, ignore_errors=True)
        os.makedirs(self.test_empty_dir, exist_ok=True)

        res = self.mgr.set_storage_path(self.test_empty_dir)
        self.assertEqual(res["storage_path"], self.test_empty_dir)

        models = self.mgr.list_models()
        for mid, m in models.items():
            self.assertFalse(m["installed"], f"Model {mid} should NOT be installed in empty directory")
            self.assertEqual(m["status"], "missing", f"Model {mid} status should be 'missing'")
            self.assertIsNone(m["local_path"])

    def test_switch_back_restores_installed_state(self):
        """
        Switch back to existing folder -> models report 'installed' again without re-downloading.
        """
        os.makedirs(self.test_empty_dir, exist_ok=True)
        self.mgr.set_storage_path(self.test_empty_dir)

        # Switch back
        self.mgr.set_storage_path(self.default_storage)
        models = self.mgr.list_models()

        # At least MP-SENet and ZipEnhancer must be installed
        self.assertTrue(models["mp_senet"]["installed"])
        self.assertEqual(models["mp_senet"]["status"], "installed")
        self.assertIsNotNone(models["mp_senet"]["local_path"])
        self.assertTrue(os.path.isfile(models["mp_senet"]["local_path"]))

    def test_migrate_copies_and_validates(self):
        """
        Test explicit migration: migrate_models copies and validates in destination.
        """
        if os.path.isdir(self.test_migrated_dir):
            shutil.rmtree(self.test_migrated_dir, ignore_errors=True)
        os.makedirs(self.test_migrated_dir, exist_ok=True)

        res = self.mgr.migrate_models(source_path=self.default_storage, target_path=self.test_migrated_dir)
        self.assertTrue(res["success"])
        self.assertGreater(res["migrated_count"], 0)

        # Setting storage to migrated directory should report models installed
        self.mgr.set_storage_path(self.test_migrated_dir)
        models = self.mgr.list_models()
        self.assertTrue(models["mp_senet"]["installed"])
        self.assertTrue(models["mp_senet"]["local_path"].startswith(self.test_migrated_dir))

if __name__ == "__main__":
    unittest.main()
