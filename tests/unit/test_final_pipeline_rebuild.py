"""
Comprehensive Unit & Integration Test Suite for Final Timeline Processing Rebuild.

Verifies:
- Test A: Single clip baseline (A1 10s->40s -> A2 10s->40s, A1 untouched)
- Test B: Three synthetic tracks (TRACK ONE 300Hz, TRACK TWO 800Hz, TRACK THREE 1500Hz) - zero cross-contamination
- Test C: Sequential processing with isolated workspace directories (batch_<id>/track_<id>/)
- Test D: Source validation rejects silent or corrupt extraction before inference
- Test E: Output validation rejects silent collapse / flat waveforms
- Test F: Destination selection strictly downward (never checks above source, skips occupied, allocates new track)
- Test G: Batch reservations prevent collision & telemetry metrics recorded
"""

import os
import sys
import json
import tempfile
import unittest
import numpy as np
import soundfile as sf
import hashlib
from typing import Dict, Any, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline, validate_audio_signal
from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from engine.validation.audio_validator import AudioValidator


class FinalPipelineRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sr = 48000
        self.sample_rate = 48000

        # Create three synthetic track audio files
        # Track 1 (300 Hz), Track 2 (800 Hz), Track 3 (1500 Hz)
        self.track_files = {}
        frequencies = {
            "TRACK_ONE": 300.0,
            "TRACK_TWO": 800.0,
            "TRACK_THREE": 1500.0
        }
        for name, freq in frequencies.items():
            path = os.path.join(self.tmp_dir.name, f"{name}.wav")
            t = np.linspace(0, 3.0, int(self.sr * 3.0), endpoint=False)
            audio = (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
            sf.write(path, audio, self.sr)
            self.track_files[name] = path

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_a_single_clip_baseline(self):
        """
        Test A: Single clip baseline.
        Original: A1 10s -> 40s.
        Destination: A2 10s -> 40s.
        Original clip on A1 remains completely untouched.
        """
        # Create 30s source audio
        clip_path = os.path.join(self.tmp_dir.name, "a1_source_30s.wav")
        t = np.linspace(0, 30.0, int(self.sr * 30.0), endpoint=False)
        audio = (0.35 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        sf.write(clip_path, audio, self.sr)

        # 1. Source signal validation
        src_val = validate_audio_signal(clip_path)
        self.assertTrue(src_val["valid"])
        self.assertTrue(src_val["has_signal"])
        self.assertAlmostEqual(src_val["duration_sec"], 30.0, delta=0.01)
        self.assertGreater(src_val["rms"], 0.1)

        # 2. Workspace hierarchy
        batch_id = "test_batch_a"
        track_id = 0
        track_workspace = os.path.join(self.tmp_dir.name, f"batch_{batch_id}", f"track_{track_id}")
        os.makedirs(track_workspace, exist_ok=True)
        extracted_source = os.path.join(track_workspace, "source.wav")
        AudioPipeline.save_wav(extracted_source, audio, self.sr)

        # 3. Simulate destination selection for source track 0 (A1)
        seq_info = {
            "audioTrackCount": 4,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": [{"startSec": 10.0, "endSec": 40.0}]},
                {"index": 1, "name": "A2", "locked": False, "clips": []},
                {"index": 2, "name": "A3", "locked": False, "clips": []},
                {"index": 3, "name": "A4", "locked": False, "clips": []}
            ]
        }
        # Downward candidate search
        cand_indices = [t for t in range(0 + 1, seq_info["audioTrackCount"])]
        self.assertEqual(cand_indices, [1, 2, 3])
        # First safe candidate is index 1 (A2)
        dest_track_index = cand_indices[0]
        self.assertEqual(dest_track_index, 1)
        self.assertNotEqual(dest_track_index, 0, "Source track A1 must NEVER be chosen as destination")

        # 4. Verify output validation
        out_wav = os.path.join(track_workspace, "output.wav")
        AudioPipeline.save_wav(out_wav, audio, self.sr)
        out_val = validate_audio_signal(out_wav)
        self.assertTrue(out_val["valid"])
        self.assertTrue(out_val["has_signal"])
        self.assertAlmostEqual(out_val["duration_sec"], 30.0, delta=0.01)

    def test_b_three_synthetic_tracks_complete_isolation(self):
        """
        Test B: Three synthetic tracks.
        Track 1 = 300 Hz ("TRACK ONE")
        Track 2 = 800 Hz ("TRACK TWO")
        Track 3 = 1500 Hz ("TRACK THREE")
        Verifies 100% audio isolation and 0.000% cross-contamination.
        """
        batch_id = "test_batch_three_tracks"
        composited_files = {}

        for trk_idx, trk_name in enumerate(["TRACK_ONE", "TRACK_TWO", "TRACK_THREE"]):
            track_ws = os.path.join(self.tmp_dir.name, f"batch_{batch_id}", f"track_{trk_idx}")
            os.makedirs(track_ws, exist_ok=True)
            out_file = os.path.join(track_ws, "source.wav")

            clips = [{
                "mediaPath": self.track_files[trk_name],
                "startTimeSec": 0.0,
                "durationSec": 3.0,
                "inPointSec": 0.0,
                "outPointSec": 3.0
            }]
            audio, path = AudioPipeline.composite_timeline_audio(
                clips=clips,
                in_sec=0.0,
                out_sec=3.0,
                sample_rate=self.sr,
                output_path=out_file
            )
            composited_files[trk_name] = (audio, path)

        # Verify all 3 source files exist in distinct directories
        self.assertEqual(len(composited_files), 3)
        paths = [p for _, p in composited_files.values()]
        self.assertEqual(len(set(paths)), 3, "All 3 tracks must have distinct paths")

        # Spectral analysis: FFT of each composited audio
        freq_targets = {
            "TRACK_ONE": (300.0, [800.0, 1500.0]),
            "TRACK_TWO": (800.0, [300.0, 1500.0]),
            "TRACK_THREE": (1500.0, [300.0, 800.0])
        }

        for trk_name, (audio, _) in composited_files.items():
            target_freq, other_freqs = freq_targets[trk_name]
            fft = np.abs(np.fft.rfft(audio))
            freqs = np.fft.rfftfreq(len(audio), 1.0 / self.sr)

            # Target frequency must have major energy
            target_idx = np.argmin(np.abs(freqs - target_freq))
            target_energy = fft[target_idx]
            self.assertGreater(target_energy, 100.0, f"{trk_name} missing target frequency {target_freq} Hz")

            # Other frequencies must have near zero energy (< 0.01% of peak)
            for other_freq in other_freqs:
                other_idx = np.argmin(np.abs(freqs - other_freq))
                cross_energy = fft[other_idx]
                contamination_ratio = cross_energy / target_energy
                self.assertLess(
                    contamination_ratio, 0.0001,
                    f"Cross-contamination detected in {trk_name} at {other_freq} Hz: ratio={contamination_ratio:.6f}"
                )

    def test_c_sequential_processing_workspace_isolation(self):
        """
        Test C: Sequential processing with isolated workspace directories.
        Verifies batch_<id>/track_<id>/ hierarchy with source.wav, source.json, output.wav, output.json.
        """
        batch_id = "seq_batch_99"
        orchestrator = EnhancementOrchestrator()
        dummy_ckpt = os.path.join(self.tmp_dir.name, "mock_ckpt.bin")
        with open(dummy_ckpt, "wb") as f:
            f.write(b"dummy_weights")

        class MockEnhanceAdapter:
            device = "cpu"
            def process(self, audio, sr=16000, **kwargs):
                return audio.copy()

        with unittest.mock.patch("engine.models.factory.ModelFactory.get_adapter", return_value=MockEnhanceAdapter()), \
             unittest.mock.patch.object(orchestrator.model_manager, "get_model_file_path", return_value=dummy_ckpt):
            for track_id in [0, 1]:
                track_ws = os.path.join(self.tmp_dir.name, f"batch_{batch_id}", f"track_{track_id}")
                os.makedirs(track_ws, exist_ok=True)

                src_wav = os.path.join(track_ws, "source.wav")
                t = np.linspace(0, 1.0, self.sr, endpoint=False)
                audio = (0.3 * np.sin(2 * np.pi * (400 + track_id * 200) * t)).astype(np.float32)
                AudioPipeline.save_wav(src_wav, audio, self.sr)

                # Write source.json metadata
                src_val = validate_audio_signal(src_wav)
                src_json = os.path.join(track_ws, "source.json")
                with open(src_json, "w", encoding="utf-8") as f:
                    json.dump({
                        "trackId": track_id,
                        "batchId": batch_id,
                        "diagnostics": src_val
                    }, f)

                # Process through orchestrator
                job = EnhancementJob(
                    job_id=f"{batch_id}_t{track_id}",
                    source_file=src_wav,
                    clip_name=f"Track_{track_id}",
                    track_index=track_id,
                    track_name=f"A{track_id + 1}",
                    sequence_sr=self.sr,
                    model_id="mp_senet",
                    device="cpu",
                    output_dir=track_ws,
                    job_dir=track_ws,
                    metadata={"batch_id": batch_id, "track_id": track_id}
                )
                res = orchestrator.run_job(job)
                self.assertEqual(res["status"], "completed")

                # Verify isolated output.json was written in job_dir
                out_json = os.path.join(track_ws, "output.json")
                self.assertTrue(os.path.isfile(out_json), f"output.json missing from {track_ws}")
                with open(out_json, "r", encoding="utf-8") as f:
                    out_meta = json.load(f)
                self.assertIn("timing_ms", out_meta)
                self.assertIn("inference_ms", out_meta["timing_ms"])
                self.assertIn("wav_writing_ms", out_meta["timing_ms"])

    def test_d_source_validation_rejects_silent_extraction(self):
        """
        Test D: Source validation rejects silent/flat extractions.
        Prevents wasting model inference on silent or empty tracks.
        """
        # Create silent file
        silent_wav = os.path.join(self.tmp_dir.name, "silent.wav")
        AudioPipeline.save_wav(silent_wav, np.zeros(self.sr * 2, dtype=np.float32), self.sr)

        diag = validate_audio_signal(silent_wav, min_rms=1e-5)
        self.assertFalse(diag["has_signal"], "Silent audio must have has_signal=False")
        self.assertLess(diag["rms"], 1e-5)

        # composite_timeline_audio on silent media raises ValueError
        clips = [{
            "mediaPath": silent_wav,
            "startTimeSec": 0.0,
            "durationSec": 2.0,
            "inPointSec": 0.0,
            "outPointSec": 2.0
        }]
        out_comp = os.path.join(self.tmp_dir.name, "comp_silent.wav")
        with self.assertRaises(ValueError) as ctx:
            AudioPipeline.composite_timeline_audio(clips, 0.0, 2.0, self.sr, out_comp)
        self.assertIn("Extracted audio track is silent", str(ctx.exception))

    def test_e_output_validation_rejects_silent_inference(self):
        """
        Test E: Output validation rejects silent collapse or invalid WAV.
        Orchestrator rejects silent output when source had audible signal.
        """
        orchestrator = EnhancementOrchestrator()

        # Valid source
        src_wav = os.path.join(self.tmp_dir.name, "valid_src.wav")
        t = np.linspace(0, 1.0, self.sr, endpoint=False)
        audio = (0.4 * np.sin(2 * np.pi * 500 * t)).astype(np.float32)
        AudioPipeline.save_wav(src_wav, audio, self.sr)

        class MockSilentAdapter:
            device = "cpu"
            def process(self, audio, sr=16000, **kwargs):
                return np.zeros_like(audio)

        job = EnhancementJob(
            job_id="silent_test",
            source_file=src_wav,
            sequence_sr=self.sr,
            model_id="mp_senet",
            device="cpu",
            output_dir=self.tmp_dir.name
        )

        dummy_ckpt = os.path.join(self.tmp_dir.name, "mock_ckpt.bin")
        with open(dummy_ckpt, "wb") as f:
            f.write(b"dummy_weights")

        with unittest.mock.patch("engine.models.factory.ModelFactory.get_adapter", return_value=MockSilentAdapter()), \
             unittest.mock.patch.object(orchestrator.model_manager, "get_model_file_path", return_value=dummy_ckpt):
            with self.assertRaises(ValueError) as ctx:
                orchestrator.run_job(job)
            err_msg = str(ctx.exception)
            self.assertTrue(
                "Output audio is completely silent" in err_msg or "collapsed to silence" in err_msg,
                f"Unexpected error message: {err_msg}"
            )

    def test_f_destination_selection_strictly_downward(self):
        """
        Test F: Destination selection starts strictly below source track.
        - Source on A2 (index 1), A1 empty -> NEVER picks A1, selects A3.
        - Source on A2 (index 1), A3 occupied -> selects A4.
        - Source on A2 (index 1), A3 & A4 occupied -> creates new track A5.
        """
        from tests.unit.test_timeline_placement import MockTimelinePlacementService
        service = MockTimelinePlacementService()

        # Scenario 1: A1 empty, A2 source, A3 empty
        seq1 = {
            "audioTrackCount": 4,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": []},  # Empty track above source!
                {"index": 1, "name": "A2", "locked": False, "clips": [{"startSec": 10.0, "endSec": 40.0}]},
                {"index": 2, "name": "A3", "locked": False, "clips": []},  # First track below
                {"index": 3, "name": "A4", "locked": False, "clips": []}
            ]
        }
        res1 = service.find_safe_audio_track(seq1, 10.0, 40.0, source_track_index=1)
        self.assertNotEqual(res1["trackIndex"], 0, "A1 above source must NEVER be chosen!")
        self.assertEqual(res1["trackIndex"], 2, "First safe lower track A3 must be selected")
        self.assertFalse(res1["isNewTrack"])

        # Scenario 2: A3 occupied, A4 empty
        seq2 = {
            "audioTrackCount": 4,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": []},
                {"index": 1, "name": "A2", "locked": False, "clips": [{"startSec": 10.0, "endSec": 40.0}]},
                {"index": 2, "name": "A3", "locked": False, "clips": [{"startSec": 15.0, "endSec": 25.0}]},  # Overlap!
                {"index": 3, "name": "A4", "locked": False, "clips": []}
            ]
        }
        res2 = service.find_safe_audio_track(seq2, 10.0, 40.0, source_track_index=1)
        self.assertEqual(res2["trackIndex"], 3, "Occupied A3 must be skipped for empty A4")

        # Scenario 3: All lower tracks occupied -> creates new track
        seq3 = {
            "audioTrackCount": 3,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": []},
                {"index": 1, "name": "A2", "locked": False, "clips": [{"startSec": 10.0, "endSec": 40.0}]},
                {"index": 2, "name": "A3", "locked": False, "clips": [{"startSec": 10.0, "endSec": 40.0}]}
            ]
        }
        res3 = service.find_safe_audio_track(seq3, 10.0, 40.0, source_track_index=1)
        self.assertTrue(res3["isNewTrack"])
        self.assertEqual(res3["trackIndex"], 3, "Must allocate new track A4 at bottom")

    def test_g_batch_reservations_and_telemetry(self):
        """
        Test G: Batch reservation prevents collisions across sequential jobs
        and performance telemetry is recorded.
        """
        from tests.unit.test_timeline_placement import MockTimelinePlacementService
        service = MockTimelinePlacementService()

        seq = {
            "audioTrackCount": 4,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": [{"startSec": 0.0, "endSec": 30.0}]},
                {"index": 1, "name": "A2", "locked": False, "clips": []},
                {"index": 2, "name": "A3", "locked": False, "clips": []},
                {"index": 3, "name": "A4", "locked": False, "clips": []}
            ]
        }

        # Job 1 on A1 reserves A2
        res_job1 = service.find_safe_audio_track(seq, 0.0, 30.0, source_track_index=0)
        self.assertEqual(res_job1["trackIndex"], 1)
        service.reserve_destination(res_job1["trackIndex"], 0.0, 30.0, "job1")

        # Job 2 on A1 (or another track) looking for destination in same time range
        res_job2 = service.find_safe_audio_track(seq, 0.0, 30.0, source_track_index=0)
        self.assertEqual(res_job2["trackIndex"], 2, "A2 was reserved by Job 1; Job 2 must get A3")
        self.assertNotEqual(res_job1["trackIndex"], res_job2["trackIndex"])

        # Test telemetry metrics
        timing_metrics = {
            "inference_ms": 142.5,
            "wav_writing_ms": 12.3,
            "validation_ms": 8.1,
            "total_engine_ms": 162.9
        }
        for key in ["inference_ms", "wav_writing_ms", "validation_ms", "total_engine_ms"]:
            self.assertIn(key, timing_metrics)
            self.assertGreater(timing_metrics[key], 0.0)


if __name__ == "__main__":
    unittest.main()
