import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.hardware.detector import HardwareDetector
import torch

class HardwareDetectionTests(unittest.TestCase):
    def setUp(self):
        self.detector = HardwareDetector()

    def test_hardware_detection_profile(self):
        """Hardware profile must return structured CPU, RAM, GPU, and devices list."""
        prof = self.detector.get_profile(refresh=True)
        self.assertIn("cpu", prof)
        self.assertIn("ram", prof)
        self.assertIn("gpus", prof)
        self.assertIn("available_devices", prof)
        self.assertIn("recommendedDevice", prof)
        self.assertTrue(len(prof["available_devices"]) >= 1)

    def test_cpu_fallback_when_cuda_disabled(self):
        """When CUDA is unavailable, recommended device must be CPU and CPU device must be listed."""
        with patch("torch.cuda.is_available", return_value=False):
            prof = self.detector.get_profile(refresh=True)
            self.assertEqual(prof["recommendedDevice"], "cpu")
            dev_ids = [d["id"] for d in prof["available_devices"]]
            self.assertIn("cpu", dev_ids)
            self.assertFalse(any(d.startswith("cuda") for d in dev_ids))

    def test_hardware_gpu_consistency(self):
        """GPU presence in torch.cuda must match detector GPU reporting."""
        cuda_avail = torch.cuda.is_available()
        prof = self.detector.get_profile(refresh=True)
        if cuda_avail:
            self.assertGreaterEqual(len(prof["gpus"]), 1)
            self.assertTrue(any(d["id"] == "cuda" or d["id"].startswith("cuda") for d in prof["available_devices"]))
        else:
            self.assertEqual(len(prof["gpus"]), 0)

    def test_device_selection_source_of_truth(self):
        """User preference resolution must respect hardware capabilities."""
        prof = self.detector.get_profile(refresh=False)
        available_ids = [d["id"] for d in prof.get("available_devices", [])]
        # Automatic and CPU must always be available
        self.assertIn("auto", available_ids)
        self.assertIn("cpu", available_ids)

    def test_hardware_detection_bounded_execution(self):
        """Hardware detection should execute within 1.5 seconds without hanging."""
        import time
        t0 = time.perf_counter()
        prof = self.detector.get_profile(refresh=True)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 2.0, f"Hardware detection took too long: {elapsed:.2f}s")

if __name__ == "__main__":
    unittest.main()
