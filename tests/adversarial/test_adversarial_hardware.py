import os
import sys
import unittest
import torch
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.hardware.detector import HardwareDetector
from models.manager import ModelManager
from engine.models.factory import ModelFactory

class AdversarialHardwareTests(unittest.TestCase):
    """
    Adversarial Hardware Matrix, Device Execution Proof, & VRAM Protection (Requirements 19, 34-37).
    """

    def setUp(self):
        self.hd = HardwareDetector()
        self.mm = ModelManager()

    def tearDown(self):
        ModelFactory.cleanup_all()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def test_device_execution_proof_actual_tensors(self):
        """Req 35: Record where actual tensors/model execute (cpu vs cuda:0). Never accept strings."""
        if not torch.cuda.is_available():
            self.skipTest("CUDA not available on this host for GPU device execution proof")

        # 1. GPU Execution Proof on MP-SENet
        ckpt_mp = self.mm.get_model_file_path("mp_senet")
        adapter_gpu = ModelFactory.create_adapter("mp_senet", ckpt_mp, device="cuda:0")
        self.assertTrue(adapter_gpu.is_initialized())

        # Inspect internal PyTorch model tensor device
        model_instance = getattr(adapter_gpu, "model", None)
        self.assertIsNotNone(model_instance, "Adapter has no model instance!")
        first_param = next(model_instance.parameters())
        self.assertEqual(first_param.device.type, "cuda", f"Expected CUDA tensor, got: {first_param.device}")
        self.assertEqual(first_param.device.index, 0)

        # 2. Force CPU Execution Proof on MP-SENet
        adapter_cpu = ModelFactory.create_adapter("mp_senet", ckpt_mp, device="cpu")
        model_cpu = getattr(adapter_cpu, "model", None)
        first_param_cpu = next(model_cpu.parameters())
        self.assertEqual(first_param_cpu.device.type, "cpu", f"Expected CPU tensor, got: {first_param_cpu.device}")

    def test_concurrent_load_and_switching_prevents_vram_exhaustion(self):
        """Req 19: Sequential loading of MossFormerGAN + MP-SENet cleans up VRAM before loading."""
        if not torch.cuda.is_available():
            self.skipTest("CUDA not available for VRAM test")

        ckpt_moss = self.mm.get_model_file_path("mossformergan")
        ckpt_mp = self.mm.get_model_file_path("mp_senet")

        # 1. Load MossFormerGAN
        adapter_moss = ModelFactory.create_adapter("mossformergan", ckpt_moss, device="cuda:0")
        self.assertTrue(adapter_moss.is_initialized())
        mem_moss = torch.cuda.memory_allocated() / (1024 ** 2)

        # 2. Switch to MP-SENet (ModelFactory must evict MossFormerGAN to avoid compound VRAM spike)
        adapter_mp = ModelFactory.create_adapter("mp_senet", ckpt_mp, device="cuda:0")
        self.assertTrue(adapter_mp.is_initialized())
        mem_mp = torch.cuda.memory_allocated() / (1024 ** 2)

        # MP-SENet footprint should be lower than MossFormerGAN without accumulating
        self.assertLess(mem_mp, mem_moss + 200.0, "VRAM accumulated without eviction of previous model!")

    def test_mossformergan_low_vram_warning_gate(self):
        """Req 36: When free VRAM < 4.5 GB, hardware profile must issue a warning for MossFormerGAN."""
        # Simulate free VRAM of only 2.5 GB
        mock_gpu = [{
            "id": "cuda:0",
            "index": 0,
            "name": "NVIDIA GeForce RTX Simulated",
            "device_name": "NVIDIA GeForce RTX Simulated",
            "vramGB": 4.0,
            "total_vram_gb": 4.0,
            "free_vram_gb": 2.5,
            "vram_total_mb": 4096.0,
            "vram_free_mb": 2560.0,
            "cuda": True,
            "available": True
        }]

        with patch.object(HardwareDetector, "detect_gpus", return_value=mock_gpu):
            hd = HardwareDetector()
            profile = hd.get_profile(refresh=True)

            self.assertIn("model_warnings", profile)
            warnings = profile["model_warnings"]
            self.assertIn("mossformergan", warnings, "Low VRAM did not trigger MossFormerGAN warning!")
            self.assertIn("4.5 GB", warnings["mossformergan"])

    def test_cpu_only_machine_simulation(self):
        """Req 37: Simulate machine with 0 NVIDIA GPUs; CPU models remain valid, GPU-only restricted."""
        with patch("torch.cuda.is_available", return_value=False):
            with patch.object(HardwareDetector, "detect_gpus", return_value=[]):
                hd = HardwareDetector()
                profile = hd.get_profile(refresh=True)

                self.assertFalse(profile["backends"]["cuda"])
                self.assertTrue(profile["backends"]["cpu"])
                self.assertEqual(len(profile["gpus"]), 0)
                self.assertEqual(profile["recommendedDevice"], "cpu")

                # Verify recommended device and available devices
                self.assertEqual(hd.get_recommended_device(), "cpu")
                devs = hd.get_available_devices()
                dev_ids = [d["id"] for d in devs]
                self.assertIn("cpu", dev_ids)
                self.assertNotIn("cuda", dev_ids, "CUDA must not be offered as an available device on a non-CUDA system!")

    def test_multi_gpu_simulation(self):
        """Req 34: Multi-GPU host properly maps and numbers cuda:0 and cuda:1."""
        mock_gpus = [
            {
                "id": "cuda:0",
                "index": 0,
                "name": "NVIDIA RTX 4090",
                "device_name": "NVIDIA RTX 4090",
                "vramGB": 24.0,
                "total_vram_gb": 24.0,
                "free_vram_gb": 20.0,
                "vram_total_mb": 24576.0,
                "vram_free_mb": 20480.0,
                "cuda": True,
                "available": True
            },
            {
                "id": "cuda:1",
                "index": 1,
                "name": "NVIDIA RTX 3080",
                "device_name": "NVIDIA RTX 3080",
                "vramGB": 10.0,
                "total_vram_gb": 10.0,
                "free_vram_gb": 8.0,
                "vram_total_mb": 10240.0,
                "vram_free_mb": 8192.0,
                "cuda": True,
                "available": True
            }
        ]

        with patch.object(HardwareDetector, "detect_gpus", return_value=mock_gpus):
            with patch("torch.cuda.is_available", return_value=True):
                hd = HardwareDetector()
                profile = hd.get_profile(refresh=True)

                self.assertEqual(len(profile["gpus"]), 2)
                self.assertEqual(profile["gpus"][0]["id"], "cuda:0")
                self.assertEqual(profile["gpus"][1]["id"], "cuda:1")
                self.assertEqual(profile["recommendedDevice"], "cuda")

if __name__ == "__main__":
    unittest.main()
