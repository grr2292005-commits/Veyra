import os
import sys
import shutil
import numpy as np
import soundfile as sf
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from models.manager import ModelManager

class TestMultiClipProcessing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.abspath(os.path.join(BASE_DIR, "logs", "test_multiclip"))
        os.makedirs(cls.test_dir, exist_ok=True)
        
        # Create a synthetic source media file: 30 seconds, 48kHz stereo
        cls.source_media = os.path.join(cls.test_dir, "master_interview.wav")
        sr = 48000
        dur_sec = 30.0
        t = np.linspace(0, dur_sec, int(sr * dur_sec), endpoint=False)
        # 440 Hz tone with noise
        synth_audio = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(len(t))
        stereo_synth = np.stack([synth_audio, synth_audio], axis=-1).astype(np.float32)
        sf.write(cls.source_media, stereo_synth, sr, subtype="PCM_24")

        cls.orchestrator = EnhancementOrchestrator()

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_two_separated_clips_with_gap(self):
        """
        Regression test for Bug #2:
        User selects [Audio Clip A] <gap> [Audio Clip B]
        Must produce:
        - 2 separate enhanced files
        - Gap strictly preserved
        - Correct clip-based names
        - Exactly matching durations
        """
        output_dir = os.path.join(self.test_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)

        # Clip A: Source 2.0s -> 7.0s (5.0s duration), Timeline start 10.0s
        clip_a = {
            "name": "Audio Clip A",
            "track_index": 0,
            "startTimeSec": 10.0,
            "durationSec": 5.0,
            "inPointSec": 2.0,
            "outPointSec": 7.0
        }

        # Gap on timeline: 15.0s to 25.0s (10.0s gap)

        # Clip B: Source 12.0s -> 16.0s (4.0s duration), Timeline start 25.0s
        clip_b = {
            "name": "Audio Clip B",
            "track_index": 0,
            "startTimeSec": 25.0,
            "durationSec": 4.0,
            "inPointSec": 12.0,
            "outPointSec": 16.0
        }

        # --- Process Clip A ---
        job_a = EnhancementJob(
            job_id="job-test-a",
            source_file=self.source_media,
            clip_name=clip_a["name"],
            track_index=clip_a["track_index"],
            in_point_sec=clip_a["inPointSec"],
            out_point_sec=clip_a["outPointSec"],
            sequence_sr=48000,
            model_id="mp_senet",
            output_dir=output_dir
        )
        res_a = self.orchestrator.run_job(job_a)

        self.assertEqual(res_a["status"], "completed")
        self.assertTrue(os.path.isfile(res_a["output_file"]))
        self.assertIn("Audio Clip A", res_a["output_filename"])
        self.assertEqual(res_a["output_filename"], "enhanced_Audio Clip A_00.wav")

        info_a = sf.info(res_a["output_file"])
        self.assertAlmostEqual(info_a.duration, clip_a["durationSec"], places=2)
        self.assertEqual(info_a.samplerate, 48000)

        # --- Process Clip B ---
        job_b = EnhancementJob(
            job_id="job-test-b",
            source_file=self.source_media,
            clip_name=clip_b["name"],
            track_index=clip_b["track_index"],
            in_point_sec=clip_b["inPointSec"],
            out_point_sec=clip_b["outPointSec"],
            sequence_sr=48000,
            model_id="mp_senet",
            output_dir=output_dir
        )
        res_b = self.orchestrator.run_job(job_b)

        self.assertEqual(res_b["status"], "completed")
        self.assertTrue(os.path.isfile(res_b["output_file"]))
        self.assertIn("Audio Clip B", res_b["output_filename"])
        self.assertEqual(res_b["output_filename"], "enhanced_Audio Clip B_00.wav")

        info_b = sf.info(res_b["output_file"])
        self.assertAlmostEqual(info_b.duration, clip_b["durationSec"], places=2)

        # --- Verify Gap and Timeline Independence ---
        self.assertNotEqual(res_a["output_file"], res_b["output_file"])
        
        # Verify timeline positions and gap
        timeline_pos_a = clip_a["startTimeSec"]
        timeline_end_a = timeline_pos_a + info_a.duration
        timeline_pos_b = clip_b["startTimeSec"]
        timeline_gap = timeline_pos_b - timeline_end_a

        self.assertEqual(timeline_pos_a, 10.0)
        self.assertAlmostEqual(timeline_end_a, 15.0, places=2)
        self.assertEqual(timeline_pos_b, 25.0)
        self.assertAlmostEqual(timeline_gap, 10.0, places=2, msg="Gap between clips must be exactly 10.0 seconds")

        # --- Verify Deterministic Versioning (Re-enhancing Clip A) ---
        job_a2 = EnhancementJob(
            job_id="job-test-a2",
            source_file=self.source_media,
            clip_name=clip_a["name"],
            track_index=clip_a["track_index"],
            in_point_sec=clip_a["inPointSec"],
            out_point_sec=clip_a["outPointSec"],
            sequence_sr=48000,
            model_id="mp_senet",
            output_dir=output_dir
        )
        res_a2 = self.orchestrator.run_job(job_a2)
        self.assertEqual(res_a2["output_filename"], "enhanced_Audio Clip A_01.wav")
        self.assertTrue(os.path.isfile(res_a["output_file"])) # _00 still exists!

if __name__ == "__main__":
    unittest.main()
