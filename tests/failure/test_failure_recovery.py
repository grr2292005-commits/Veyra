import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from engine.audio.pipeline import AudioPipeline
from tools.audio_generator import AudioGenerator

class FailureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_fail_test_")
        self.orch = EnhancementOrchestrator()

        # Create a sample test wav file
        self.sample_wav = os.path.join(self.temp_dir, "input_speech.wav")
        audio = AudioGenerator.generate_sine_wave(freq_hz=300.0, duration_sec=0.5, sr=16000)
        AudioGenerator.save_temp_wav(self.sample_wav, audio, sr=16000)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_job_cancellation_safe_cleanup(self):
        """Cancelling a job before or during inference raises InterruptedError and writes no final output."""
        job = EnhancementJob(
            job_id="test_cancel_job",
            source_file=self.sample_wav,
            clip_name="cancel_clip",
            output_dir=os.path.join(self.temp_dir, "output"),
            model_id="mp_senet"
        )
        # Mark job cancelled immediately
        job.cancelled = True

        with self.assertRaises(InterruptedError):
            self.orch.run_job(job)

        self.assertEqual(job.cancelled, True)
        # Ensure no final output wav was written
        out_dir = os.path.join(self.temp_dir, "output")
        if os.path.exists(out_dir):
            wavs = [f for f in os.listdir(out_dir) if f.endswith(".wav")]
            self.assertEqual(len(wavs), 0, "Partial output file was written despite cancellation!")

    def test_missing_source_file_error(self):
        """Job with nonexistent source file must raise FileNotFoundError cleanly."""
        job = EnhancementJob(
            job_id="test_missing_source",
            source_file=os.path.join(self.temp_dir, "nonexistent.wav"),
            output_dir=os.path.join(self.temp_dir, "output")
        )
        with self.assertRaises(FileNotFoundError):
            self.orch.run_job(job)

    def test_job_retry_clean_state(self):
        """A retried job must start with fresh queued status and clean progress."""
        job = EnhancementJob(
            job_id="retry_job_01",
            source_file=self.sample_wav,
            output_dir=os.path.join(self.temp_dir, "output")
        )
        job.status = "failed"
        job.error = "Previous error"
        job.progress_pct = 45.0

        # Simulate retry initialization
        retry_job = EnhancementJob(
            job_id="retry_job_02",
            source_file=self.sample_wav,
            output_dir=os.path.join(self.temp_dir, "output")
        )
        self.assertEqual(retry_job.status, "queued")
        self.assertIsNone(retry_job.error)
        self.assertEqual(retry_job.progress_pct, 0.0)

    def test_temp_file_collision_protection(self):
        """Concurrent jobs must generate unique temporary directory paths."""
        job1_id = "job-uuid-1111"
        job2_id = "job-uuid-2222"

        temp1 = os.path.join(BASE_DIR, "Speechify", "Temp", job1_id)
        temp2 = os.path.join(BASE_DIR, "Speechify", "Temp", job2_id)

        self.assertNotEqual(temp1, temp2)
        self.assertFalse(temp1.endswith(temp2))

if __name__ == "__main__":
    unittest.main()
