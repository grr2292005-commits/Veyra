import unittest
import os
import sys
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from engine.models.factory import ModelFactory

class TestModelAdapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = ModelManager()

    def test_mp_senet_inference_and_cleanup(self):
        info = self.mgr.get_model("mp_senet")
        if not info or not info.get("installed"):
            self.skipTest("MP-SENet not seeded in model storage")

        adapter = ModelFactory.create_adapter("mp_senet", info["path"])
        adapter.load()

        # 1.0s synthetic signal at 16kHz
        sr = 16000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        signal = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(sr)).astype(np.float32)

        enhanced = adapter.enhance(signal, sr)
        self.assertEqual(len(enhanced), len(signal))
        self.assertFalse(np.isnan(enhanced).any())

        adapter.unload()

    def test_zipenhancer_inference_and_cleanup(self):
        info = self.mgr.get_model("zipenhancer")
        if not info or not info.get("installed"):
            self.skipTest("ZipEnhancer-S not seeded in model storage")

        adapter = ModelFactory.create_adapter("zipenhancer", info["path"])
        adapter.load()

        sr = 16000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        signal = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(sr)).astype(np.float32)

        enhanced = adapter.enhance(signal, sr)
        self.assertEqual(len(enhanced), len(signal))
        self.assertFalse(np.isnan(enhanced).any())

        adapter.unload()

    def test_deepfilternet3_inference_and_cleanup(self):
        info = self.mgr.get_model("deepfilternet3")
        if not info or not info.get("installed"):
            self.skipTest("DeepFilterNet3 not seeded in model storage")

        adapter = ModelFactory.create_adapter("deepfilternet3", info["path"])
        adapter.load()

        # DeepFilterNet3 operates natively at 48kHz
        sr = 48000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        signal = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(sr)).astype(np.float32)

        enhanced = adapter.enhance(signal, sr)
        self.assertEqual(len(enhanced), len(signal))
        self.assertFalse(np.isnan(enhanced).any())

        adapter.unload()

if __name__ == "__main__":
    unittest.main()
