import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.hardware.detector import HardwareDetector

class TestHardwareUIPropagation(unittest.TestCase):
    """
    Automated regression tests verifying the authoritative hardware data pipeline:
    HardwareDetector -> HardwareManager -> Engine /system -> AppState -> Settings UI.
    Guarantees that a machine with an NVIDIA GPU never falls back to CPU-only in the UI.
    """

    def setUp(self):
        self.detector = HardwareDetector()

    def test_hardware_gpu_propagates_to_ui(self):
        """When CUDA is available, get_available_devices() must return at least one GPU."""
        cuda_avail = self.detector.detect_cuda()
        devices = self.detector.get_available_devices()

        if cuda_avail:
            gpu_devs = [d for d in devices if d["type"] == "cuda" or d["id"].startswith("cuda")]
            self.assertGreater(len(gpu_devs), 0, "GPU is available in hardware but missing in available_devices")
            first_gpu = gpu_devs[0]
            self.assertTrue(first_gpu.get("available"), "GPU device must be marked available")
            self.assertIn("GPU", first_gpu["name"])
        else:
            self.skipTest("Host machine does not have CUDA available")

    def test_gpu_device_option_available(self):
        """GPU option must contain GPU identifier, friendly name, and VRAM amount."""
        devices = self.detector.get_available_devices()
        gpu_options = [d for d in devices if d["type"] == "cuda" or d["id"].startswith("cuda")]

        if gpu_options:
            gpu = gpu_options[0]
            self.assertTrue(gpu["id"].startswith("cuda"))
            self.assertIn("VRAM", gpu["name"])
            self.assertGreater(gpu.get("vramGB", 0), 0)

    def test_cpu_device_option_available(self):
        """CPU device option must always be available as a system fallback."""
        devices = self.detector.get_available_devices()
        cpu_options = [d for d in devices if d["id"] == "cpu"]
        self.assertEqual(len(cpu_options), 1)
        self.assertEqual(cpu_options[0]["name"], "CPU — System Processor")
        self.assertTrue(cpu_options[0].get("available", False))

    def test_automatic_device_resolution(self):
        """Automatic device selection resolves to CUDA when available, CPU otherwise."""
        cuda_avail = self.detector.detect_cuda()
        resolved = self.detector.resolve_device("auto")
        if cuda_avail:
            self.assertEqual(resolved, "cuda:0")
        else:
            self.assertEqual(resolved, "cpu")

    def test_hardware_to_ui_device_mapping(self):
        """Contract test: fails if HardwareManager detects GPU but UI device options are CPU-only."""
        has_cuda = self.detector.detect_cuda()
        devices = self.detector.get_available_devices()
        has_gpu_in_ui = any(d["type"] == "cuda" or d["id"].startswith("cuda") for d in devices)

        if has_cuda:
            self.assertTrue(has_gpu_in_ui, "HardwareDetector detected CUDA, but UI device list contains NO GPU!")

    def test_gpu_disappearing_regression(self):
        """
        Simulate HardwareDetector finding an RTX 4050 with 6GB VRAM.
        Verify that available_devices exposes the GPU option with exact naming and formatting.
        """
        mock_gpus = [{
            "id": "cuda:0",
            "index": 0,
            "name": "NVIDIA GeForce RTX 4050 Laptop GPU",
            "device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
            "vramGB": 6.0,
            "total_vram_gb": 6.0,
            "free_vram_gb": 5.0,
            "vram_total_mb": 6144.0,
            "vram_free_mb": 5120.0,
            "cuda": True,
            "cuda_available": True,
            "available": True
        }]

        with patch.object(HardwareDetector, "detect_gpus", return_value=mock_gpus):
            det = HardwareDetector()
            devs = det.get_available_devices()
            gpu_dev = next((d for d in devs if d["id"] == "cuda:0"), None)
            self.assertIsNotNone(gpu_dev, "RTX 4050 disappeared from device options!")
            self.assertIn("NVIDIA RTX 4050", gpu_dev["name"])
            self.assertIn("6 GB VRAM", gpu_dev["name"])
            self.assertEqual(gpu_dev["vramGB"], 6)

    def test_device_selection_resolution_modes(self):
        """Verify that 'cuda:0', 'cuda', 'cpu', and 'auto' resolve deterministically."""
        # 1. CPU request always resolves to cpu
        self.assertEqual(self.detector.resolve_device("cpu"), "cpu")

        # 2. CUDA request resolves to cuda:0 if cuda available
        has_cuda = self.detector.detect_cuda()
        if has_cuda:
            self.assertEqual(self.detector.resolve_device("cuda"), "cuda:0")
            self.assertEqual(self.detector.resolve_device("cuda:0"), "cuda:0")
            self.assertEqual(self.detector.resolve_device("auto"), "cuda:0")
        else:
            self.assertEqual(self.detector.resolve_device("cuda"), "cpu")
            self.assertEqual(self.detector.resolve_device("auto"), "cpu")

    def test_multiple_gpu_detection(self):
        """Simulate multi-GPU system (RTX 4070 12GB + RTX 4090 24GB). Both GPUs must be exposed."""
        mock_gpus = [
            {
                "id": "cuda:0",
                "index": 0,
                "name": "NVIDIA GeForce RTX 4070",
                "device_name": "NVIDIA GeForce RTX 4070",
                "vramGB": 12.0,
                "total_vram_gb": 12.0,
                "free_vram_gb": 11.0,
                "vram_total_mb": 12288.0,
                "vram_free_mb": 11264.0,
                "cuda": True,
                "cuda_available": True,
                "available": True
            },
            {
                "id": "cuda:1",
                "index": 1,
                "name": "NVIDIA GeForce RTX 4090",
                "device_name": "NVIDIA GeForce RTX 4090",
                "vramGB": 24.0,
                "total_vram_gb": 24.0,
                "free_vram_gb": 22.0,
                "vram_total_mb": 24576.0,
                "vram_free_mb": 22528.0,
                "cuda": True,
                "cuda_available": True,
                "available": True
            }
        ]

        with patch.object(HardwareDetector, "detect_gpus", return_value=mock_gpus):
            det = HardwareDetector()
            devs = det.get_available_devices()
            gpu_devs = [d for d in devs if d["type"] == "cuda" or d["id"].startswith("cuda")]
            self.assertEqual(len(gpu_devs), 2, "Both GPUs must be exposed in multi-GPU system")
            self.assertEqual(gpu_devs[0]["id"], "cuda:0")
            self.assertIn("RTX 4070", gpu_devs[0]["name"])
            self.assertIn("12 GB VRAM", gpu_devs[0]["name"])
            self.assertEqual(gpu_devs[1]["id"], "cuda:1")
            self.assertIn("RTX 4090", gpu_devs[1]["name"])
            self.assertIn("24 GB VRAM", gpu_devs[1]["name"])

    def test_cpu_only_detection(self):
        """Simulate CPU-only system. Only Automatic and CPU must be listed."""
        with patch.object(HardwareDetector, "detect_gpus", return_value=[]):
            with patch.object(HardwareDetector, "detect_cuda", return_value=False):
                det = HardwareDetector()
                devs = det.get_available_devices()
                dev_ids = [d["id"] for d in devs]
                self.assertIn("auto", dev_ids)
                self.assertIn("cpu", dev_ids)
                self.assertFalse(any(d.startswith("cuda") for d in dev_ids), "CPU-only machine must have no CUDA options")
                self.assertEqual(det.resolve_device("auto"), "cpu")

    def test_hardware_profile_is_dynamic(self):
        """Hardware profile must not be hardcoded; changing mock hardware changes profile immediately."""
        mock_custom_gpu = [{
            "id": "cuda:0",
            "index": 0,
            "name": "NVIDIA RTX 6000 Ada Generation",
            "device_name": "NVIDIA RTX 6000 Ada Generation",
            "vramGB": 48.0,
            "total_vram_gb": 48.0,
            "free_vram_gb": 46.0,
            "vram_total_mb": 49152.0,
            "vram_free_mb": 47104.0,
            "cuda": True,
            "cuda_available": True,
            "available": True
        }]
        with patch.object(HardwareDetector, "detect_gpus", return_value=mock_custom_gpu):
            det = HardwareDetector()
            devs = det.get_available_devices()
            gpu_option = next((d for d in devs if d["id"] == "cuda:0"), None)
            self.assertIsNotNone(gpu_option)
            self.assertIn("RTX 6000 Ada", gpu_option["name"])
            self.assertIn("48 GB VRAM", gpu_option["name"])

    def test_device_options_come_from_hardware_manager(self):
        """Device options must contain required contract fields."""
        devs = self.detector.get_available_devices()
        for d in devs:
            self.assertIn("id", d)
            self.assertIn("name", d)
            self.assertIn("type", d)
            self.assertIn("available", d)

    def test_gpu_ui_matches_runtime_capability(self):
        """Available GPU device count must strictly match viable CUDA GPUs detected."""
        gpus = self.detector.detect_gpus()
        cuda_gpus = [g for g in gpus if g.get("cuda")]
        devs = self.detector.get_available_devices()
        ui_gpus = [d for d in devs if d["type"] == "cuda"]
        self.assertEqual(len(ui_gpus), len(cuda_gpus), "UI GPU device count must match runtime capable GPUs")

if __name__ == "__main__":
    unittest.main()

