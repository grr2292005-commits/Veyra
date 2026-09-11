import os
import sys
import torch
import numpy as np
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.models.factory import ModelFactory
from models.manager import ModelManager

class TestDeviceSelection(unittest.TestCase):
    def setUp(self):
        self.mgr = ModelManager()
        self.meta = self.mgr.registry_data["models"]["mp_senet"]
        self.ckpt = self.mgr.get_model_file_path("mp_senet")
        self.assertIsNotNone(self.ckpt, "MP-SENet checkpoint required for device testing")

    def tearDown(self):
        ModelFactory.cleanup_all()

    def test_cpu_device_selection(self):
        """Forces CPU execution, verifies model parameters are on CPU."""
        adapter = ModelFactory.get_adapter("mp_senet", self.meta, self.ckpt, device="cpu")
        self.assertEqual(str(adapter.device), "cpu")
        
        # Test forward pass on CPU
        dummy = np.zeros(16000, dtype=np.float32)
        out = adapter.process(dummy, sr=16000)
        self.assertEqual(len(out), 16000)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA not available on this machine")
    def test_cuda_device_selection(self):
        """Forces CUDA execution, verifies model parameters are on GPU."""
        adapter = ModelFactory.get_adapter("mp_senet", self.meta, self.ckpt, device="cuda")
        self.assertIn("cuda", str(adapter.device))
        
        # Test forward pass on GPU
        dummy = np.zeros(16000, dtype=np.float32)
        out = adapter.process(dummy, sr=16000)
        self.assertEqual(len(out), 16000)

    def test_device_switch_reinitializes(self):
        """Verifies that switching from CPU to GPU or vice versa reinitializes cleanly."""
        adapter_cpu = ModelFactory.get_adapter("mp_senet", self.meta, self.ckpt, device="cpu")
        self.assertEqual(str(adapter_cpu.device), "cpu")

        if torch.cuda.is_available():
            adapter_gpu = ModelFactory.get_adapter("mp_senet", self.meta, self.ckpt, device="cuda")
            self.assertIn("cuda", str(adapter_gpu.device))

if __name__ == "__main__":
    unittest.main()
