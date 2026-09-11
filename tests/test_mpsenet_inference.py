import unittest
import os
import sys
import tempfile
import soundfile as sf
import numpy as np
import torch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from models.manager import ModelManager

class TestMPSENetInference(unittest.TestCase):
    def test_mpsenet_end_to_end(self):
        mgr = ModelManager()
        orch = EnhancementOrchestrator(mgr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1-second 48kHz audio snippet
            sr = 48000
            test_wav = os.path.join(tmp_dir, "test_in.wav")
            audio = np.random.uniform(-0.2, 0.2, sr).astype(np.float32)
            sf.write(test_wav, audio, sr)

            job = EnhancementJob(
                job_id="test-mpsenet-001",
                source_file=test_wav,
                in_point_sec=0.0,
                out_point_sec=1.0,
                sequence_sr=48000,
                model_id="mp_senet",
                output_dir=tmp_dir
            )

            orch.run_job(job)
            self.assertEqual(job.status, "completed")
            self.assertIsNotNone(job.result)
            enhanced_file = job.result["enhanced_file"]
            self.assertTrue(os.path.exists(enhanced_file))
            info = sf.info(enhanced_file)
            self.assertEqual(info.samplerate, 48000)
            print("\nMP-SENet End-to-End verified successfully on device:", job.result.get("device"))

if __name__ == "__main__":
    unittest.main()
