import unittest
import os
import sys
import tempfile
import numpy as np
import soundfile as sf

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline
from engine.validation.audio_validator import AudioValidator, AudioValidationError

class TestAudioPipelineAndValidation(unittest.TestCase):
    def setUp(self):
        self.pipeline = AudioPipeline()
        self.validator = AudioValidator(max_duration_drift_ms=45.0)
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_versioned_filename_generation(self):
        source = os.path.join(self.tmp_dir.name, "interview_clip.mp4")
        name0 = self.pipeline.get_versioned_filename(self.tmp_dir.name, "interview_clip.mp4")
        self.assertEqual(os.path.basename(name0), "enhanced_interview_clip_00.wav")

        # Create 00.wav and test that next is 01.wav
        open(name0, "w").close()
        name1 = self.pipeline.get_versioned_filename(self.tmp_dir.name, "interview_clip.mp4")
        self.assertEqual(os.path.basename(name1), "enhanced_interview_clip_01.wav")

    def test_resampling_precision_roundtrip(self):
        sr_orig = 48000
        sr_model = 16000
        duration_sec = 2.0
        t = np.linspace(0, duration_sec, int(duration_sec * sr_orig), endpoint=False)
        # 1 kHz test sine wave
        sine_48k = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

        # Downsample 48k -> 16k
        sine_16k = self.pipeline.resample(sine_48k, sr_orig, sr_model)
        expected_len_16k = int(duration_sec * sr_model)
        self.assertAlmostEqual(len(sine_16k), expected_len_16k, delta=2)

        # Upsample 16k -> 48k
        sine_48k_reconstructed = self.pipeline.resample(sine_16k, sr_model, sr_orig)
        self.assertAlmostEqual(len(sine_48k_reconstructed), len(sine_48k), delta=4)

        # Check correlation between original and reconstructed
        corr = np.corrcoef(sine_48k[:len(sine_48k_reconstructed)], sine_48k_reconstructed)[0, 1]
        self.assertGreater(corr, 0.99)

    def test_export_wav_24bit_pcm(self):
        sr = 48000
        audio = np.random.uniform(-0.5, 0.5, sr).astype(np.float32)
        out_path = os.path.join(self.tmp_dir.name, "test_24bit.wav")

        self.pipeline.save_wav(out_path, audio, sr, subtype="PCM_24")
        self.assertTrue(os.path.exists(out_path))

        info = sf.info(out_path)
        self.assertEqual(info.samplerate, 48000)
        self.assertEqual(info.subtype, "PCM_24")
        self.assertEqual(info.channels, 1)

    def test_audio_validator_success(self):
        sr = 48000
        raw = np.random.uniform(-0.6, 0.6, sr).astype(np.float32)
        enh = np.random.uniform(-0.5, 0.5, sr).astype(np.float32)

        val_res = self.validator.validate(raw, enh, sr, sr)
        self.assertTrue(val_res["valid"])
        self.assertLess(val_res["duration_drift_ms"], 1.0)
        self.assertFalse(val_res["has_clipping"])

    def test_audio_validator_drift_guard(self):
        sr = 48000
        raw = np.random.uniform(-0.5, 0.5, sr).astype(np.float32) # 1.0s
        # 1.1s (100ms discrepancy > 45ms tolerance)
        enh = np.random.uniform(-0.5, 0.5, int(sr * 1.1)).astype(np.float32)

        with self.assertRaises(AudioValidationError) as ctx:
            self.validator.validate(raw, enh, sr, sr, raise_on_error=True)
        self.assertIn("mismatch", str(ctx.exception).lower())

    def test_audio_validator_nan_inf_guard(self):
        sr = 48000
        raw = np.zeros(sr, dtype=np.float32)
        enh = np.ones(sr, dtype=np.float32)
        enh[500] = np.nan

        with self.assertRaises(AudioValidationError) as ctx:
            self.validator.validate(raw, enh, sr, sr, raise_on_error=True)
        self.assertIn("nan", str(ctx.exception).lower())

if __name__ == "__main__":
    unittest.main()
