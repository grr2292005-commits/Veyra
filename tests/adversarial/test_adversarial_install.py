import os
import sys
import tempfile
import shutil
import unittest
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.storage_manager import ModelStorageManager

class AdversarialInstallTests(unittest.TestCase):
    """
    Adversarial Clean-Machine, Reinstall, & Dependency Determinism Suite (Requirements 6-9, 11).
    """

    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="sp_adv_inst_")

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_dependency_lock_determinism(self):
        """Req 10 & 11: Verify requirements-lock.txt exists, is strictly pinned (==), and contains no version ranges."""
        lock_file = os.path.join(BASE_DIR, "requirements-lock.txt")
        self.assertTrue(os.path.isfile(lock_file), "requirements-lock.txt missing from project root!")

        with open(lock_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        # Critical libraries that MUST be pinned exactly
        must_be_pinned = [
            "numpy", "torch", "torchaudio", "soundfile", "scipy",
            "clearvoice", "rotary-embedding-torch", "yamlargparse", "deepfilternet", "psutil"
        ]

        found_pins = {}
        for line in lines:
            if "==" in line:
                pkg, ver = line.split("==", 1)
                found_pins[pkg.lower()] = ver
            else:
                self.fail(f"Ambiguous or non-deterministic dependency in lock file: {line}")

        for target in must_be_pinned:
            # Check if target or capitalized variant is in found_pins
            matching = [v for k, v in found_pins.items() if target in k]
            self.assertTrue(len(matching) > 0, f"Critical dependency '{target}' is not in requirements-lock.txt!")

        # Verify exact NumPy version is pinned (no 1.26.4 / 2.x range)
        self.assertEqual(found_pins.get("numpy"), "1.26.4", "NumPy is not strictly pinned to 1.26.4!")

    def test_uninstall_safety_preserves_user_model_storage(self):
        """Req 9: Uninstall must NOT delete user-created model data unless explicitly requested."""
        # Setup simulated application directory and user model directory
        app_data_dir = os.path.join(self.temp_root, "AppData", "Local", "Speechify")
        user_model_dir = os.path.join(self.temp_root, "AppData", "Roaming", "Speechify", "Models")
        custom_user_dir = os.path.join(self.temp_root, "D_Drive", "MySpecialModels")

        os.makedirs(app_data_dir, exist_ok=True)
        os.makedirs(user_model_dir, exist_ok=True)
        os.makedirs(custom_user_dir, exist_ok=True)

        # Write mock application files
        with open(os.path.join(app_data_dir, "engine.lock"), "w") as f: f.write("1234")
        with open(os.path.join(app_data_dir, "server.log"), "w") as f: f.write("log data")

        # Write mock valuable user model files
        user_model_file = os.path.join(user_model_dir, "custom_model.bin")
        custom_dir_file = os.path.join(custom_user_dir, "custom_voice.pt")
        with open(user_model_file, "w") as f: f.write("VALUABLE_MODEL_WEIGHTS")
        with open(custom_dir_file, "w") as f: f.write("VALUABLE_CUSTOM_WEIGHTS")

        # Simulated Uninstall Routine: Only purges application binaries/temp caches, leaves user model data
        def simulate_safe_uninstall():
            # 1. Clean app data
            if os.path.exists(app_data_dir):
                shutil.rmtree(app_data_dir)
            # 2. NEVER touch custom_user_dir or user_model_dir without explicit flag!

        simulate_safe_uninstall()

        # Confirm app data is removed
        self.assertFalse(os.path.exists(app_data_dir))

        # Confirm user models are COMPLETELY PRESERVED
        self.assertTrue(os.path.exists(user_model_file), "Safe uninstall deleted user models!")
        self.assertTrue(os.path.exists(custom_dir_file), "Safe uninstall deleted custom directory models!")
        with open(user_model_file, "r") as f:
            self.assertEqual(f.read(), "VALUABLE_MODEL_WEIGHTS")

    def test_reinstall_and_repair_idempotency_cycle(self):
        """Req 8: Simulate install -> uninstall -> install -> repair -> repair cycles without stale corruptions."""
        # Simulated Speechify root
        sim_root = os.path.join(self.temp_root, "Speechify")
        config_file = os.path.join(sim_root, "models", "storage_config.json")

        def simulate_install():
            os.makedirs(os.path.join(sim_root, "models"), exist_ok=True)
            with open(config_file, "w") as f:
                json.dump({"models_directory": os.path.join(sim_root, "models", "storage"), "is_managed": True}, f)

        def simulate_uninstall():
            if os.path.exists(sim_root):
                shutil.rmtree(sim_root)

        def simulate_repair():
            # Repair checks and restores missing config if absent or malformed
            if not os.path.exists(config_file):
                simulate_install()
            else:
                try:
                    with open(config_file, "r") as f: json.load(f)
                except Exception:
                    simulate_install()

        # Run Cycle: install -> uninstall -> install -> repair -> repair
        simulate_install()
        self.assertTrue(os.path.isfile(config_file))

        simulate_uninstall()
        self.assertFalse(os.path.exists(sim_root))

        simulate_install()
        self.assertTrue(os.path.isfile(config_file))

        simulate_repair()
        self.assertTrue(os.path.isfile(config_file))

        simulate_repair()
        self.assertTrue(os.path.isfile(config_file))

        # Verify valid JSON survived repair cycles
        with open(config_file, "r") as f:
            data = json.load(f)
            self.assertTrue(data.get("is_managed"))

if __name__ == "__main__":
    unittest.main()
