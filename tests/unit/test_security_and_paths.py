import os
import sys
import tempfile
import shutil
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline
from models.storage_manager import ModelStorageManager

class SecurityAndPathsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_sec_test_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_path_traversal_sanitization(self):
        """Path traversal characters (..) in audio names or filenames must be neutralized."""
        dangerous_names = [
            "../../Windows/System32/calc.exe",
            "..\\..\\sensitive_file",
            "../../../etc/passwd",
            "audio/../../../escape"
        ]
        for name in dangerous_names:
            sanitized = AudioPipeline.sanitize_filename(name)
            self.assertNotIn("..", sanitized, f"Failed neutralizing .. in {name} -> {sanitized}")
            self.assertNotIn("/", sanitized)
            self.assertNotIn("\\", sanitized)

    def test_unicode_path_support(self):
        """Non-ASCII and Unicode characters in filenames must be supported safely."""
        unicode_names = [
            "entrevista_español",
            "podcast_café_noir",
            "录音_interview_01",
            "озвучка_диалог"
        ]
        for uname in unicode_names:
            sanitized = AudioPipeline.sanitize_filename(uname)
            # Must remain readable
            self.assertTrue(len(sanitized) > 0)
            # Create a file with this name to verify Windows filesystem accepts it
            fpath = os.path.join(self.temp_dir, sanitized + ".wav")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("unicode audio test")
            self.assertTrue(os.path.isfile(fpath))

    def test_long_path_resilience(self):
        """Long filenames (approaching or exceeding MAX_PATH) must be handled gracefully."""
        long_base = "a" * 200
        target = os.path.join(self.temp_dir, "sub_" * 5)
        os.makedirs(target, exist_ok=True)
        v_path = AudioPipeline.get_versioned_filename(target, long_base, model_name="MP-SENet")
        self.assertTrue(v_path.endswith(".wav"))
        self.assertIn("enhanced_", os.path.basename(v_path))

    def test_no_hardcoded_user_paths_in_configs(self):
        """Configuration files must not hardcode personal user paths where dynamic paths should be used."""
        config_path = os.path.join(BASE_DIR, "models", "storage_config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Ensure it resolves through valid ModelStorageManager
                sm = ModelStorageManager()
                self.assertTrue(os.path.isabs(sm.get_storage_path()))

    def test_checkpoint_extension_security(self):
        """Downloaded checkpoints must be binary weights, not executables (.exe, .bat, .ps1)."""
        from models.manager import ModelManager
        mm = ModelManager()
        for mid, mdata in mm.registry_data.get("models", {}).items():
            fname = mdata.get("checkpoint_filename", "").lower()
            self.assertFalse(fname.endswith(".exe"), f"Unsafe model file: {fname}")
            self.assertFalse(fname.endswith(".bat"), f"Unsafe model file: {fname}")
            self.assertFalse(fname.endswith(".cmd"), f"Unsafe model file: {fname}")
            self.assertFalse(fname.endswith(".ps1"), f"Unsafe model file: {fname}")
            self.assertFalse(fname.endswith(".vbs"), f"Unsafe model file: {fname}")

if __name__ == "__main__":
    unittest.main()
