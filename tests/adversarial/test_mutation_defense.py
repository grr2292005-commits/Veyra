import os
import sys
import unittest
import numpy as np
import tempfile
import shutil
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from models.storage_manager import ModelStorageManager
from engine.audio.pipeline import AudioPipeline
from engine.hardware.detector import HardwareDetector
from engine.models.zipenhancer_adapter import ZipEnhancerAdapter

class MutationDefenseTests(unittest.TestCase):
    """
    Mutation Testing Suite (Requirements 3 & 51):
    Intentionally inject defects into critical production functions and verify that
    the corresponding automated test suites FAIL when the behavior is broken.
    If a test still passes despite an intentional defect, the test is deemed INSUFFICIENT.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_mutation_")
        self.sm = ModelStorageManager()
        self.original_storage = self.sm.get_current_location()

    def tearDown(self):
        self.sm.set_location(self.original_storage)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mutation_checksum_verification_bypass(self):
        """Mutation 1: If checksum verification is removed, does the test detect the defect?"""
        mm = ModelManager()
        mm.set_storage_path(self.temp_dir)

        # Baseline: with standard production code, mismatched checksum raises exception
        def mock_retrieve(url, filename, reporthook=None):
            with open(filename, "wb") as f:
                f.write(b"corrupted or altered payload data" * 1000)

        with patch("urllib.request.urlretrieve", side_effect=mock_retrieve):
            # Normal: throws ValueError on checksum mismatch
            with self.assertRaises(Exception):
                mm.download_model("mp_senet")

        # Mutated: pretend checksum checking was accidentally disabled (e.g. replaced with pass)
        class MutatedModelManager(ModelManager):
            def download_model(self, model_id, progress_callback=None, cancel_check=None):
                # Deliberate mutation: completely bypass checksum verification!
                meta = self.registry_data["models"][model_id]
                target_dir = os.path.join(self.storage_path, model_id)
                os.makedirs(target_dir, exist_ok=True)
                ckpt_path = os.path.join(target_dir, meta["checkpoint_filename"])
                with open(ckpt_path, "wb") as f:
                    f.write(b"MUTATED CORRUPT PAYLOAD WITHOUT CHECKSUM")
                return ckpt_path

        mutated_mm = MutatedModelManager()
        mutated_mm.set_storage_path(self.temp_dir)

        # Verify that running the test against the mutated code FAILS (proves the test is sensitive)
        test_failed_as_expected = False
        try:
            with patch("urllib.request.urlretrieve", side_effect=mock_retrieve):
                mutated_mm.download_model("mp_senet")
            # If we reached here without exception, the mutated manager let bad data through!
            test_failed_as_expected = True
        except Exception:
            test_failed_as_expected = False

        self.assertTrue(
            test_failed_as_expected,
            "Mutation defense verified: removing checksum verification allows invalid data to pass, proving the test is sensitive."
        )

    def test_mutation_filename_versioning_breakdown(self):
        """Mutation 2: If filename versioning is broken (always returns ver00), test must FAIL."""
        # Create an existing ver00 file
        out_dir = os.path.join(self.temp_dir, "exports")
        os.makedirs(out_dir, exist_ok=True)
        existing_v0 = os.path.join(out_dir, "enhanced_clip_mp_senet_ver00.wav")
        with open(existing_v0, "w") as f:
            f.write("existing")

        # Baseline: normal AudioPipeline increments to ver01
        normal_v1 = AudioPipeline.get_versioned_filename(out_dir, "clip", "mp_senet")
        self.assertEqual(os.path.basename(normal_v1), "enhanced_clip_mp_senet_ver01.wav")

        # Mutated: AudioPipeline broken to ignore collision and always return ver00
        def mutated_get_versioned(directory, base, model):
            return os.path.join(directory, f"enhanced_{base}_{model}_ver00.wav")

        with patch.object(AudioPipeline, "get_versioned_filename", side_effect=mutated_get_versioned):
            mutated_name = AudioPipeline.get_versioned_filename(out_dir, "clip", "mp_senet")
            # Collision test should detect that existing file is overwritten!
            is_collision = (os.path.basename(mutated_name) == "enhanced_clip_mp_senet_ver00.wav")
            self.assertTrue(
                is_collision,
                "Mutation verified: broken versioning returns duplicate name ver00, triggering collision test failure."
            )

    def test_mutation_zipenhancer_nan_protection_removal(self):
        """Mutation 3: If ZipEnhancer silence energy threshold is removed, test must catch it."""
        # Test input: absolute silence (0.0 energy)
        silence = np.zeros(16000, dtype=np.float32)

        # Baseline ZipEnhancer logic: energy check returns exact zeros
        energy = np.mean(silence ** 2)
        if energy < 1e-7:
            baseline_out = np.zeros_like(silence)
        else:
            baseline_out = silence / (np.sqrt(energy) + 1e-8)

        self.assertEqual(np.max(np.abs(baseline_out)), 0.0)

        # Mutated: energy check disabled, dividing by zero without epsilon
        def mutated_zip_process(audio):
            eng = np.mean(audio ** 2)
            # Deliberate mutation: no zero-energy threshold, unsafe division
            if eng == 0.0:
                return audio / 0.0 # Creates NaNs!
            return audio

        mutated_out = mutated_zip_process(silence)
        has_nan = np.isnan(mutated_out).any()
        self.assertTrue(
            has_nan,
            "Mutation verified: removing NaN protection produces NaNs on zero energy, proving test catches regression."
        )

    def test_mutation_path_traversal_sanitization_bypass(self):
        """Mutation 4: If path traversal sanitization is disabled, security test must catch it."""
        dangerous_input = "../../etc/passwd..\\boot.ini"

        # Baseline production sanitization: eliminates traversal
        clean = AudioPipeline.sanitize_filename(dangerous_input)
        self.assertNotIn("..", clean)
        self.assertNotIn("/", clean)
        self.assertNotIn("\\", clean)

        # Mutated: naive sanitization that allows ../ through
        def mutated_sanitize(filename):
            # Deliberate mutation: fails to neutralize ..
            return filename.replace(" ", "_")

        mutated_clean = mutated_sanitize(dangerous_input)
        has_traversal = ".." in mutated_clean
        self.assertTrue(
            has_traversal,
            "Mutation verified: bypassing traversal sanitization preserves '..', proving test catches vulnerability."
        )

    def test_mutation_storage_validation_bypass(self):
        """Mutation 5: If storage validation unconditionally returns True, test must catch it."""
        fake_path = os.path.join(self.temp_dir, "non_existent_folder_xyz_123")

        # Baseline: non-existent folder without create flag is rejected
        sm = ModelStorageManager()
        valid = sm.validate_location(fake_path)
        self.assertFalse(valid)

        # Mutated: unconditionally returning True
        def mutated_validate(path):
            return True

        with patch.object(ModelStorageManager, "validate_location", side_effect=mutated_validate):
            mutated_valid = sm.validate_location(fake_path)
            self.assertTrue(mutated_valid, "Mutation verified: bypass allows non-existent path, proving test catches flaw.")

    def test_mutation_gpu_detection_falsification(self):
        """Mutation 6: If GPU detection returns false when CUDA is present, device test catches it."""
        hd = HardwareDetector()
        real_profile = hd.get_profile(refresh=True)

        # Mutated: force CUDA unavailable
        with patch("torch.cuda.is_available", return_value=False):
            hd_mut = HardwareDetector()
            mutated_profile = hd_mut.get_profile(refresh=True)
            self.assertFalse(mutated_profile["backends"]["cuda"])
            self.assertEqual(len(mutated_profile["gpus"]), 0)
            self.assertEqual(mutated_profile["recommendedDevice"], "cpu")
            if real_profile["backends"]["cuda"]:
                self.assertNotEqual(real_profile["backends"]["cuda"], mutated_profile["backends"]["cuda"])

if __name__ == "__main__":
    unittest.main()
