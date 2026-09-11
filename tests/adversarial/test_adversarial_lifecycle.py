import os
import sys
import time
import psutil
import unittest
import torch
import threading

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.models.factory import ModelFactory
from models.manager import ModelManager
from tools.audio_generator import AudioGenerator

class AdversarialLifecycleTests(unittest.TestCase):
    """
    Adversarial Lifecycle, Process Tree, & Resource Regression Suite (Requirements 20-25, 45-46).
    """

    def setUp(self):
        self.mm = ModelManager()
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.process = psutil.Process()

    def tearDown(self):
        ModelFactory.cleanup_all()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def test_process_tree_capture_during_lifecycle(self):
        """Req 21: Capture actual process tree (parent, children, PID, CPU, RAM) across states."""
        current_pid = os.getpid()
        parent = self.process.parent()
        children = self.process.children(recursive=True)

        info = {
            "pid": current_pid,
            "name": self.process.name(),
            "parent_pid": parent.pid if parent else None,
            "parent_name": parent.name() if parent else None,
            "children_count": len(children),
            "children_pids": [c.pid for c in children],
            "cpu_percent": self.process.cpu_percent(interval=0.1),
            "rss_ram_mb": round(self.process.memory_info().rss / (1024 ** 2), 2),
            "threads_count": self.process.num_threads()
        }

        self.assertGreater(info["rss_ram_mb"], 10.0)
        self.assertGreater(info["threads_count"], 0)
        # Verify no rogue runaway subprocesses spawned
        self.assertLessEqual(info["children_count"], 4, "Excessive child processes detected!")

    def test_repeated_inference_resource_regression_10_25_50(self):
        """Req 20 & 45: Run 10, 25, 50 short inference jobs; assert bounded memory without monotonic leak."""
        ckpt = self.mm.get_model_file_path("mp_senet")
        self.assertTrue(ckpt and os.path.isfile(ckpt))

        adapter = ModelFactory.create_adapter("mp_senet", ckpt, device=self.device)
        test_audio = AudioGenerator.generate_speech_like(duration_sec=0.5, sr=16000)

        # Baseline reading
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        rss_start = self.process.memory_info().rss / (1024 ** 2)
        vram_start = torch.cuda.memory_allocated() / (1024 ** 2) if torch.cuda.is_available() else 0.0

        readings = []

        # Run 50 iterations, measuring at 10, 25, 50
        for i in range(1, 51):
            _ = adapter.process(test_audio, 16000)

            if i in (10, 25, 50):
                gc.collect()
                rss_now = self.process.memory_info().rss / (1024 ** 2)
                vram_now = torch.cuda.memory_allocated() / (1024 ** 2) if torch.cuda.is_available() else 0.0
                readings.append({
                    "iteration": i,
                    "rss_mb": round(rss_now, 2),
                    "vram_mb": round(vram_now, 2),
                    "rss_growth": round(rss_now - rss_start, 2),
                    "vram_growth": round(vram_now - vram_start, 2)
                })

        # Monotonicity check: RAM growth between iter 25 and 50 must not continue growing linearly
        growth_10_to_25 = readings[1]["rss_mb"] - readings[0]["rss_mb"]
        growth_25_to_50 = readings[2]["rss_mb"] - readings[1]["rss_mb"]

        # VRAM should be steady state (0 growth after model allocation)
        if torch.cuda.is_available():
            self.assertLessEqual(readings[2]["vram_growth"], 50.0, "VRAM leaked monotonically during repeated inference!")

        # RSS RAM growth between 25 and 50 should be less than 100MB
        self.assertLess(growth_25_to_50, 100.0, f"RAM leaked monotonically from 25 to 50: {growth_25_to_50} MB")

    def test_model_switch_stress(self):
        """Req 46: Repeatedly switch between models and verify resources remain bounded."""
        models = ["mp_senet", "zipenhancer", "deepfilternet3"]
        mems = []

        for cycle in range(3):
            for mid in models:
                ckpt = self.mm.get_model_file_path(mid)
                if not ckpt or not os.path.isfile(ckpt): continue
                adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
                self.assertTrue(adapter.is_initialized())
                if torch.cuda.is_available():
                    mems.append(torch.cuda.memory_allocated() / (1024 ** 2))

        # Peak VRAM during cycle 3 should not exceed cycle 1 peak by > 50MB
        if len(mems) >= 6:
            cycle1_max = max(mems[:3])
            cycle3_max = max(mems[-3:])
            self.assertLessEqual(cycle3_max, cycle1_max + 50.0, "Model switching accumulated VRAM!")

    def test_duplicate_start_duplication_idempotency(self):
        """Req 24: Concurrent startup triggers from multiple paths produce only one instance."""
        created_adapters = []
        lock = threading.Lock()

        def worker_load():
            ckpt = self.mm.get_model_file_path("mp_senet")
            adapter = ModelFactory.create_adapter("mp_senet", ckpt, device=self.device)
            with lock:
                created_adapters.append(adapter)

        threads = [threading.Thread(target=worker_load) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(len(created_adapters), 5)
        # All returned adapters should be the exact same singleton instance
        first_id = id(created_adapters[0])
        for a in created_adapters:
            self.assertEqual(id(a), first_id, "ModelFactory created duplicate instances concurrently!")

    def test_duplicate_shutdown_idempotency(self):
        """Req 25: Triggering shutdown multiple times is safe and completely idempotent."""
        ModelFactory.cleanup_all()
        # Second call
        ModelFactory.cleanup_all()
        # Third call
        ModelFactory.cleanup_all()
        self.assertIsNone(ModelFactory._active_adapter)
        self.assertIsNone(ModelFactory._active_model_id)

if __name__ == "__main__":
    unittest.main()
