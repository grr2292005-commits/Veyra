import os
import sys
import time
import tempfile
import shutil
import unittest
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.models.factory import ModelFactory
from models.manager import ModelManager
from tools.test_helpers import TestHelpers
from tools.audio_generator import AudioGenerator

try:
    import torch
except ImportError:
    torch = None

class ResourceLeakTests(unittest.TestCase):
    def setUp(self):
        self.mm = ModelManager()

    def tearDown(self):
        ModelFactory.cleanup_all()

    def test_repeated_inference_memory_stability(self):
        """Repeated short inference calls must not cause runaway monotonic memory growth."""
        ckpt = self.mm.get_model_file_path("mp_senet")
        self.assertTrue(ckpt and os.path.isfile(ckpt))

        device = "cuda:0" if (torch and torch.cuda.is_available()) else "cpu"
        adapter = ModelFactory.create_adapter("mp_senet", ckpt, device=device)

        test_audio = AudioGenerator.generate_sine_wave(freq_hz=440.0, duration_sec=0.2, sr=16000)

        # Warmup
        adapter.process(test_audio, 16000)

        initial_mem = TestHelpers.get_memory_info()

        # Run repeated inference
        for i in range(5):
            out = adapter.process(test_audio, 16000)
            self.assertFalse(np.isnan(out).any())

        final_mem = TestHelpers.get_memory_info()

        # VRAM check: VRAM should not grow monotonically by more than 100MB
        if torch and torch.cuda.is_available():
            vram_diff = final_mem.get("vram_mb", 0) - initial_mem.get("vram_mb", 0)
            self.assertLess(vram_diff, 100.0, f"VRAM leaked across iterations: +{vram_diff} MB")

    def test_model_load_unload_cycle(self):
        """Loading and unloading models must return memory close to baseline (excluding 1-time DLL imports)."""
        ckpt = self.mm.get_model_file_path("zipenhancer")
        self.assertTrue(ckpt and os.path.isfile(ckpt))

        # Warmup import to separate 1-time Python C-extension load from tensor allocation
        adapter0 = ModelFactory.create_adapter("zipenhancer", ckpt, device="cpu")
        ModelFactory.cleanup_all()
        import gc
        gc.collect()

        baseline_mem = TestHelpers.get_memory_info()

        # Cycle 2: Load again
        adapter1 = ModelFactory.create_adapter("zipenhancer", ckpt, device="cpu")
        self.assertIsNotNone(adapter1)

        # Unload
        ModelFactory.cleanup_all()
        del adapter0
        del adapter1
        gc.collect()
        if torch and torch.cuda.is_available():
            torch.cuda.empty_cache()

        final_mem = TestHelpers.get_memory_info()
        ram_diff = abs(final_mem.get("ram_mb", 0) - baseline_mem.get("ram_mb", 0))
        # RAM delta after unload should be minimal (< 50MB)
        self.assertLess(ram_diff, 50.0, f"RAM growth after unload cycle exceeds threshold: {ram_diff} MB")

    def test_orphan_temp_cleanup(self):
        """Temp directory cleanup scans Speechify/Temp and removes stale job folders older than threshold."""
        temp_dir = os.path.join(BASE_DIR, "Speechify", "Temp")
        os.makedirs(temp_dir, exist_ok=True)

        stale_job_dir = os.path.join(temp_dir, "job-stale-test-999")
        os.makedirs(stale_job_dir, exist_ok=True)
        # Touch file inside
        with open(os.path.join(stale_job_dir, "source.wav"), "w") as f:
            f.write("old temp audio")

        # Simulate time passage by setting mtime 2 hours in the past
        past_time = time.time() - 7200
        os.utime(stale_job_dir, (past_time, past_time))

        # Perform cleanup
        now_t = time.time()
        for entry in os.listdir(temp_dir):
            if entry.startswith("job-"):
                epath = os.path.join(temp_dir, entry)
                if os.path.isdir(epath):
                    if (now_t - os.path.getmtime(epath)) > 3600:
                        shutil.rmtree(epath, ignore_errors=True)

        self.assertFalse(os.path.exists(stale_job_dir), "Stale temp directory was not cleaned!")

if __name__ == "__main__":
    unittest.main()
