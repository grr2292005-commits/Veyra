import unittest
import sys
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.hardware.detector import HardwareDetector

class TestHardwareDetector(unittest.TestCase):
    def setUp(self):
        self.detector = HardwareDetector()

    def test_cpu_detection(self):
        cpu_info = self.detector.detect_cpu()
        self.assertIn("name", cpu_info)
        self.assertIn("physical_cores", cpu_info)
        self.assertIn("logical_cores", cpu_info)
        self.assertGreater(cpu_info["logical_cores"], 0)

    def test_ram_detection(self):
        ram_info = self.detector.detect_ram()
        self.assertIn("total_gb", ram_info)
        self.assertIn("available_gb", ram_info)
        self.assertGreater(ram_info["total_gb"], 0)

    def test_gpu_detection(self):
        gpu_info = self.detector.detect_gpu()
        self.assertIn("available", gpu_info)
        if gpu_info["available"]:
            self.assertIn("device_name", gpu_info)
            self.assertIn("total_vram_gb", gpu_info)
            self.assertIn("free_vram_gb", gpu_info)
            self.assertGreater(gpu_info["total_vram_gb"], 0)

    def test_tier_classification_rtx4050(self):
        profile = self.detector.get_profile(refresh=True)
        self.assertIn("recommended_tier", profile)
        self.assertIn("recommended_model", profile)
        # On user machine with RTX 4050 6GB VRAM, tier should be B or A
        if profile["gpu"]["available"]:
            self.assertIn(profile["recommended_tier"], ["A", "B"])
            self.assertEqual(profile["recommended_model"], "mp_senet")

    def test_tier_classification_synthetic_gpu_tiers(self):
        # Test synthetic tiers
        tier_high = self.detector._classify_hardware(
            {"available": True, "total_vram_gb": 16.0, "free_vram_gb": 14.0},
            {"total_gb": 64.0}
        )
        self.assertEqual(tier_high["tier"], "A")
        self.assertEqual(tier_high["recommended_model"], "mp_senet")

        tier_entry = self.detector._classify_hardware(
            {"available": True, "total_vram_gb": 4.0, "free_vram_gb": 3.2},
            {"total_gb": 16.0}
        )
        self.assertEqual(tier_entry["tier"], "B")

        tier_cpu = self.detector._classify_hardware(
            {"available": False, "total_vram_gb": 0.0, "free_vram_gb": 0.0},
            {"total_gb": 16.0}
        )
        self.assertEqual(tier_cpu["tier"], "D")
        self.assertEqual(tier_cpu["recommended_model"], "deepfilternet3")

if __name__ == "__main__":
    unittest.main()
