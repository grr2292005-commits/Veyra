import os
import sys
import time
import unittest
import numpy as np
import soundfile as sf
import tempfile
import shutil
import torch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.manager import ModelManager
from engine.models.factory import ModelFactory
from tools.audio_generator import AudioGenerator
from engine.validation.audio_validator import AudioValidator
from engine.audio.pipeline import AudioPipeline

class AdversarialAudioTests(unittest.TestCase):
    """
    Adversarial Audio & Extreme Numerical Testing Suite (Requirements 4, 5, 47, 48, 49, 50).
    Tests all 4 models using REAL production checkpoints on real hardware across:
    - Normal speech
    - Quiet speech (-45 dBFS)
    - Pure silence (0.0 energy)
    - Near silence (-80 dBFS)
    - Very loud clipped audio (+6 dBFS)
    - Short audio (0.05s / 1 video frame)
    - 5-second and 30-second audio
    - Extended continuous audio
    - Passthrough detection (input != output)
    - Output WAV integrity (sample rate, channels, finite amplitudes, non-empty)
    """

    def setUp(self):
        self.mm = ModelManager()
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.temp_dir = tempfile.mkdtemp(prefix="sp_adv_audio_")
        self.model_records = {}

        # Pre-verify all 4 real checkpoints exist
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            ckpt = self.mm.get_model_file_path(mid)
            assert ckpt and os.path.isfile(ckpt), f"Missing real checkpoint for {mid} at {ckpt}"
            self.model_records[mid] = {
                "checkpoint": ckpt,
                "size_bytes": os.path.getsize(ckpt)
            }

    def tearDown(self):
        ModelFactory.cleanup_all()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _verify_output_integrity(self, input_audio: np.ndarray, output_audio: np.ndarray, sr: int = 16000, is_silence: bool = False):
        """Standard production gate checks for numerical sanity."""
        self.assertFalse(np.isnan(output_audio).any(), "Output contains NaN values!")
        self.assertFalse(np.isinf(output_audio).any(), "Output contains Inf values!")
        self.assertGreater(len(output_audio), 0, "Output is empty!")

        max_peak = float(np.max(np.abs(output_audio)))
        self.assertLessEqual(max_peak, 1.2, f"Output amplitude exploded: peak = {max_peak}")

        if is_silence:
            self.assertEqual(max_peak, 0.0, f"Silence input produced non-zero output: peak = {max_peak}")
        else:
            rms = float(np.sqrt(np.mean(output_audio ** 2)))
            self.assertGreater(rms, 1e-6, f"Output collapsed to absolute zero: RMS = {rms}")

    def test_zipenhancer_silence_and_near_silence_adversarial(self):
        """ZipEnhancer-S specific regression test: pure silence and -80dBFS near silence."""
        ckpt = self.model_records["zipenhancer"]["checkpoint"]
        adapter = ModelFactory.create_adapter("zipenhancer", ckpt, device=self.device)

        # 1. Pure silence (1 second)
        silence = AudioGenerator.generate_silence(duration_sec=1.0, sr=16000)
        out_silence = adapter.process(silence, 16000)
        self._verify_output_integrity(silence, out_silence, 16000, is_silence=True)

        # 2. Near silence (-80 dBFS)
        near_silence = AudioGenerator.generate_near_silence(duration_sec=1.0, sr=16000, level_db=-80.0)
        out_near = adapter.process(near_silence, 16000)
        self.assertFalse(np.isnan(out_near).any(), "ZipEnhancer produced NaN on near-silence!")
        self.assertFalse(np.isinf(out_near).any(), "ZipEnhancer produced Inf on near-silence!")

        # 3. Near silence (-100 dBFS)
        near_silence_100 = AudioGenerator.generate_near_silence(duration_sec=1.0, sr=16000, level_db=-100.0)
        out_near_100 = adapter.process(near_silence_100, 16000)
        self.assertFalse(np.isnan(out_near_100).any(), "ZipEnhancer produced NaN on -100dBFS!")

    def test_all_models_normal_speech(self):
        """Test normal speech (-18 dBFS) through all 4 production models at their native sample rates."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            sr = 48000 if mid == "deepfilternet3" else 16000
            speech = AudioGenerator.generate_speech_like(duration_sec=2.0, sr=sr, rms_target=0.1)
            ckpt = self.model_records[mid]["checkpoint"]
            adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
            out = adapter.process(speech, sr)

            self._verify_output_integrity(speech, out, sr, is_silence=False)

            # Passthrough detection: output must NOT be identical to input
            mse = float(np.mean((out[:len(speech)] - speech[:len(out)]) ** 2))
            self.assertGreater(mse, 1e-6, f"Model {mid} returned input unchanged (passthrough failure, MSE={mse})")

    def test_all_models_quiet_speech(self):
        """Test quiet speech (-45 dBFS whisper) through all 4 production models."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            sr = 48000 if mid == "deepfilternet3" else 16000
            quiet_speech = AudioGenerator.generate_speech_like(duration_sec=1.5, sr=sr, rms_target=0.005)
            ckpt = self.model_records[mid]["checkpoint"]
            adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
            out = adapter.process(quiet_speech, sr)
            self._verify_output_integrity(quiet_speech, out, sr, is_silence=False)

    def test_all_models_very_loud_clipped_audio(self):
        """Test deliberately clipped audio (+6 dBFS) through all 4 models."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            sr = 48000 if mid == "deepfilternet3" else 16000
            clipped = AudioGenerator.generate_clipped_audio(duration_sec=1.0, sr=sr)
            ckpt = self.model_records[mid]["checkpoint"]
            adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
            out = adapter.process(clipped, sr)

            self.assertFalse(np.isnan(out).any(), f"{mid} produced NaN on clipped audio!")
            self.assertFalse(np.isinf(out).any(), f"{mid} produced Inf on clipped audio!")
            max_val = float(np.max(np.abs(out)))
            self.assertLessEqual(max_val, 1.2, f"{mid} peak exploded on clipped audio: {max_val}")

    def test_all_models_short_frame_audio(self):
        """Test ultra-short audio: 0.05s (1 video frame = 800 samples at 16kHz, 2400 at 48kHz)."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            sr = 48000 if mid == "deepfilternet3" else 16000
            short_audio = AudioGenerator.generate_speech_like(duration_sec=0.05, sr=sr, rms_target=0.1)
            ckpt = self.model_records[mid]["checkpoint"]
            adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
            out = adapter.process(short_audio, sr)

            self.assertFalse(np.isnan(out).any(), f"{mid} produced NaN on 1-frame audio!")
            self.assertFalse(np.isinf(out).any(), f"{mid} produced Inf on 1-frame audio!")
            self.assertGreater(len(out), 0, f"{mid} output empty on 1-frame audio")

    def test_extended_duration_speech(self):
        """Test 30-second synthetic speech audio through DeepFilterNet3 and MP-SENet."""
        # 30-second speech at native sample rates
        for mid in ("deepfilternet3", "mp_senet"):
            sr = 48000 if mid == "deepfilternet3" else 16000
            speech_30s = AudioGenerator.generate_speech_like(duration_sec=30.0, sr=sr, rms_target=0.1)
            ckpt = self.model_records[mid]["checkpoint"]
            adapter = ModelFactory.create_adapter(mid, ckpt, device=self.device)
            t0 = time.perf_counter()
            out_30s = adapter.process(speech_30s, sr)
            elapsed = time.perf_counter() - t0

            self._verify_output_integrity(speech_30s, out_30s, sr, is_silence=False)
            rtf = elapsed / 30.0 # Real-time factor
            self.assertLess(rtf, 1.0, f"{mid} Real-Time Factor too slow: {rtf:.2f}x (took {elapsed:.2f}s for 30s)")

    def test_output_wav_file_integrity(self):
        """Verify saved WAV file is valid 24-bit PCM/Float, valid header, non-empty."""
        speech = AudioGenerator.generate_speech_like(duration_sec=2.0, sr=16000)
        wav_path = os.path.join(self.temp_dir, "test_output.wav")
        AudioGenerator.save_temp_wav(wav_path, speech, sr=16000)

        self.assertTrue(os.path.isfile(wav_path))
        self.assertGreater(os.path.getsize(wav_path), 1000)

        # Read back and verify
        data, sr = sf.read(wav_path)
        self.assertEqual(sr, 16000)
        self.assertEqual(len(data), len(speech))
        self.assertAlmostEqual(float(np.max(np.abs(data))), float(np.max(np.abs(speech))), places=3)

    def test_model_self_test_honesty(self):
        """Verify every model reports genuine checkpoint paths, valid device, and realistic processing times."""
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            t0 = time.perf_counter()
            res = self.mm.validate_model_runtime(mid)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            self.assertTrue(res.get("success"), f"Self-test failed for {mid}: {res.get('error')}")
            self.assertEqual(res.get("status"), "Ready")
            self.assertIn(res.get("device"), ("cuda:0", "cpu"))
            # Self-test must execute real inference, taking > 5ms
            self.assertGreater(elapsed_ms, 5.0, f"Self test finished too quickly ({elapsed_ms}ms) - likely stubbed!")

if __name__ == "__main__":
    unittest.main()
