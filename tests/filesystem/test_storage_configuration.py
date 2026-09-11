import os
import sys
import json
import tempfile
import shutil
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.storage_manager import ModelStorageManager

class StorageConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="sp_storage_test_")
        self.original_config_path = os.path.join(BASE_DIR, "models", "storage_config.json")
        # Backup original config if present
        self.backup_config = None
        if os.path.isfile(self.original_config_path):
            with open(self.original_config_path, "r", encoding="utf-8") as f:
                self.backup_config = f.read()

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)
        # Restore original config
        if self.backup_config is not None:
            with open(self.original_config_path, "w", encoding="utf-8") as f:
                f.write(self.backup_config)

    def test_existing_valid_folder(self):
        """Test valid folder is marked accessible and readable/writable."""
        valid_dir = os.path.join(self.temp_root, "valid_models")
        os.makedirs(valid_dir, exist_ok=True)
        sm = ModelStorageManager()
        cap = sm.get_storage_capabilities(valid_dir)
        self.assertTrue(cap["exists"])
        self.assertTrue(cap["readable"])
        self.assertTrue(cap["writable"])
        self.assertTrue(cap["valid"])

    def test_empty_folder(self):
        """Empty folder must report 0 models and never silently copy files."""
        empty_dir = os.path.join(self.temp_root, "empty_models")
        os.makedirs(empty_dir, exist_ok=True)
        sm = ModelStorageManager()
        res = sm.set_storage_path(empty_dir)
        self.assertEqual(res["models_count"], 0)
        self.assertEqual(len(os.listdir(empty_dir)), 0, "Empty folder was silently populated!")

    def test_file_instead_of_folder(self):
        """Using a file path as model storage should fail validation cleanly."""
        dummy_file = os.path.join(self.temp_root, "dummy.txt")
        with open(dummy_file, "w") as f:
            f.write("not a folder")
        sm = ModelStorageManager()
        cap = sm.get_storage_capabilities(dummy_file)
        self.assertFalse(cap["exists"])
        self.assertFalse(cap["valid"])
        self.assertFalse(sm.validate_location(dummy_file))

    def test_storage_capabilities_model(self):
        """Verify storage capability returns exists, readable, writable, models_installed."""
        test_dir = os.path.join(self.temp_root, "cap_test")
        os.makedirs(test_dir, exist_ok=True)
        sm = ModelStorageManager()
        cap = sm.get_storage_capabilities(test_dir)
        self.assertIn("exists", cap)
        self.assertIn("readable", cap)
        self.assertIn("writable", cap)
        self.assertIn("models_installed", cap)
        self.assertIn("valid", cap)
        self.assertEqual(cap["models_installed"], 0)

    def test_storage_path_change_race(self):
        """Path A -> B -> C immediately: final state must be C, with incremented version."""
        path_a = os.path.join(self.temp_root, "path_a")
        path_b = os.path.join(self.temp_root, "path_b")
        path_c = os.path.join(self.temp_root, "path_c")
        os.makedirs(path_a, exist_ok=True)
        os.makedirs(path_b, exist_ok=True)
        os.makedirs(path_c, exist_ok=True)

        sm = ModelStorageManager()
        res_a = sm.set_storage_path(path_a)
        res_b = sm.set_storage_path(path_b)
        res_c = sm.set_storage_path(path_c)

        self.assertEqual(os.path.normcase(sm.get_storage_path()), os.path.normcase(path_c))
        self.assertGreater(res_c["operation_version"], res_b["operation_version"])
        self.assertGreater(res_b["operation_version"], res_a["operation_version"])

    def test_atomic_configuration_writes(self):
        """Verify configuration writes are atomic and no temp files are leaked."""
        sm = ModelStorageManager()
        test_dir = os.path.join(self.temp_root, "atomic_dir")
        os.makedirs(test_dir, exist_ok=True)
        sm.set_storage_path(test_dir)

        # Config file must exist and be valid JSON
        self.assertTrue(os.path.isfile(sm.config_path))
        with open(sm.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(os.path.normcase(data["models_directory"]), os.path.normcase(test_dir))

        # Check no .tmp files leaked in models directory
        models_dir = os.path.dirname(sm.config_path)
        tmp_files = [f for f in os.listdir(models_dir) if f.startswith(sm.CONFIG_FILENAME + ".tmp")]
        self.assertEqual(len(tmp_files), 0, "Atomic temporary config files were leaked!")

    def test_corrupted_configuration_recovery(self):
        """Verify corrupted/malformed configuration files recover safely to sane defaults."""
        config_file = os.path.join(BASE_DIR, "models", "storage_config.json")
        malformed_inputs = [
            "",                        # Empty file
            "{{{ invalid json",        # Malformed JSON
            "{}",                      # Empty dict
            json.dumps({"models_directory": 12345}), # Wrong data type
            json.dumps({"models_directory": ""}),    # Empty string
            json.dumps({"models_directory": "Z:\\nonexistent\\forbidden\\path\\1234"}) # Inaccessible path
        ]

        for malformed in malformed_inputs:
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(malformed)
            
            # Instantiation must NOT crash and must restore a valid managed location
            sm = ModelStorageManager()
            self.assertTrue(os.path.isdir(sm.get_storage_path()))
            self.assertTrue(sm.get_storage_capabilities()["valid"])

    def test_folder_deleted_after_configuration(self):
        """If configured storage folder is deleted externally, validate_location notices cleanly."""
        del_dir = os.path.join(self.temp_root, "to_delete")
        os.makedirs(del_dir, exist_ok=True)
        sm = ModelStorageManager()
        sm.set_storage_path(del_dir)
        self.assertTrue(sm.validate_location(del_dir))

        # Delete externally
        shutil.rmtree(del_dir, ignore_errors=True)
        self.assertFalse(sm.validate_location(del_dir))
        cap = sm.get_storage_capabilities(del_dir)
        self.assertFalse(cap["exists"])
        self.assertFalse(cap["valid"])

if __name__ == "__main__":
    unittest.main()
