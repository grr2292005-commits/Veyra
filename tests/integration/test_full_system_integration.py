import os
import sys
import tempfile
import shutil
import unittest
import numpy as np
import soundfile as sf

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from engine.audio.pipeline import AudioPipeline
from models.manager import ModelManager
from tools.audio_generator import AudioGenerator

class FullSystemIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_integ_test_")
        self.orch = EnhancementOrchestrator()
        self.mm = ModelManager()

        # Generate a test input WAV file (48kHz stereo, 1 second)
        self.input_wav = os.path.join(self.temp_dir, "podcast_interview.wav")
        stereo_audio = AudioGenerator.generate_stereo(duration_sec=1.0, sr=48000)
        AudioGenerator.save_temp_wav(self.input_wav, stereo_audio, sr=48000)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_enhancement_workflow(self):
        """Complete workflow: extract -> resample -> infer -> validate -> save broadcast WAV with versioning."""
        output_dir = os.path.join(self.temp_dir, "Enhanced_Audio")
        job = EnhancementJob(
            job_id="integ_job_001",
            source_file=self.input_wav,
            clip_name="podcast_interview",
            sequence_sr=48000,
            model_id="mp_senet",
            device="auto",
            output_dir=output_dir
        )

        progress_reports = []
        def _prog(pct, msg):
            progress_reports.append((pct, msg))

        result = self.orch.run_job(job, progress_cb=_prog)

        # 1. Status and metrics
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_id"], "mp_senet")
        self.assertEqual(result["sample_rate"], 48000)
        self.assertIn("enhanced_file", result)
        self.assertTrue(os.path.isfile(result["enhanced_file"]))

        # 2. Filename must strictly follow naming policy: enhanced_{audio}_{model}_ver00.wav
        expected_name = "enhanced_podcast_interview_MP-SENet_ver00.wav"
        self.assertEqual(result["output_filename"], expected_name)

        # 3. Audio file integrity
        data, sr = sf.read(result["enhanced_file"])
        self.assertEqual(sr, 48000)
        self.assertFalse(np.isnan(data).any())
        self.assertFalse(np.isinf(data).any())
        self.assertGreater(len(data), 0)

        # 4. Progress reports must span from start to 100%
        self.assertGreater(len(progress_reports), 3)
        self.assertEqual(progress_reports[-1][0], 100.0)

    def test_timeline_multiclip_compositing(self):
        """Verify multi-clip timeline compositing into a single continuous broadcast sequence audio."""
        clip1_path = os.path.join(self.temp_dir, "clip1.wav")
        clip2_path = os.path.join(self.temp_dir, "clip2.wav")

        AudioGenerator.save_temp_wav(clip1_path, AudioGenerator.generate_sine_wave(freq_hz=440.0, duration_sec=0.5, sr=48000), sr=48000)
        AudioGenerator.save_temp_wav(clip2_path, AudioGenerator.generate_sine_wave(freq_hz=880.0, duration_sec=0.5, sr=48000), sr=48000)

        clips = [
            {
                "media_path": clip1_path,
                "start_time_sec": 0.0,
                "duration_sec": 0.5,
                "in_point_sec": 0.0,
                "out_point_sec": 0.5
            },
            {
                "media_path": clip2_path,
                "start_time_sec": 1.0, # 0.5s gap on timeline
                "duration_sec": 0.5,
                "in_point_sec": 0.0,
                "out_point_sec": 0.5
            }
        ]

        composite_out = os.path.join(self.temp_dir, "composite.wav")
        composite_audio, path = AudioPipeline.composite_timeline_audio(
            clips=clips,
            in_sec=0.0,
            out_sec=1.5,
            sample_rate=48000,
            output_path=composite_out
        )

        self.assertTrue(os.path.isfile(composite_out))
        self.assertEqual(len(composite_audio), int(1.5 * 48000))
        # Timeline gap check: between 0.5s and 1.0s (samples 24000 to 48000) must be silence
        gap_samples = composite_audio[24000:48000]
        self.assertEqual(np.max(np.abs(gap_samples)), 0.0, "Timeline gap was not preserved as silence!")

if __name__ == "__main__":
    unittest.main()
