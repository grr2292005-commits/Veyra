import unittest
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.runtime.model_discovery import ModelDiscovery
from models.manager import ModelManager

class TestModelDiscovery(unittest.TestCase):
    def setUp(self):
        self.discovery = ModelDiscovery()

    def test_search_roots_resolved(self):
        roots = self.discovery.scan_roots
        self.assertTrue(len(roots) > 0)
        # Verify roots are real directories
        for r in roots:
            self.assertTrue(os.path.isdir(r), f"Root {r} should be a valid directory")

    def test_checkpoint_validation_rules(self):
        # Fake non-existent path
        valid, msg = self.discovery.validate_checkpoint("mp_senet", "non_existent_file.pt")
        self.assertFalse(valid)
        self.assertIn("does not exist", msg)

    def test_scan_finds_models(self):
        found = self.discovery.scan()
        # Verify MP-SENet and ZipEnhancer are detected from disk
        self.assertIn("mp_senet", found)
        self.assertIn("zipenhancer", found)

        mp_info = found["mp_senet"]
        self.assertTrue(os.path.isfile(mp_info["checkpoint_path"]))
        self.assertTrue(mp_info["validated"])
        self.assertGreater(mp_info["size_bytes"], 1_000_000)

    def test_model_manager_integration(self):
        mgr = ModelManager()
        models = mgr.list_models()
        self.assertIn("mp_senet", models)
        self.assertTrue(models["mp_senet"]["installed"])
        self.assertTrue(models["mp_senet"]["validated"])
        self.assertTrue(os.path.isfile(models["mp_senet"]["local_path"]))

        self.assertIn("zipenhancer", models)
        self.assertTrue(models["zipenhancer"]["installed"])

if __name__ == "__main__":
    unittest.main()
