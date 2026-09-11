import os
import sys
import tempfile
import shutil
import unittest
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline
from engine.validation.audio_validator import AudioValidator
from tools.audio_generator import AudioGenerator

class AudioPipelineAndNamingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sp_audio_test_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_naming_policy_strict(self):
        """Verify output naming: enhanced_{audio_file_name}_{model_name}_ver{xx}.wav"""
        target = self.temp_dir
        base = "podcast_audio"
        model = "MP-SENet"

        p0 = AudioPipeline.get_versioned_filename(target, base, model_name=model)
        self.assertEqual(os.path.basename(p0), "enhanced_podcast_audio_MP-SENet_ver00.wav")

        # Create ver00 file on disk
        with open(p0, "w") as f: f.write("0")

        p1 = AudioPipeline.get_versioned_filename(target, base, model_name=model)
        self.assertEqual(os.path.basename(p1), "enhanced_podcast_audio_MP-SENet_ver01.wav")

        with open(p1, "w") as f: f.write("1")

        p2 = AudioPipeline.get_versioned_filename(target, base, model_name=model)
        self.assertEqual(os.path.basename(p2), "enhanced_podcast_audio_MP-SENet_ver02.wav")

    def test_audio_name_sanitization(self):
        """Test sanitization of illegal Windows characters, spaces, and colons."""
        cases = [
            ("Podcast Audio", "Podcast Audio"),
            ("Podcast/Audio", "Podcast_Audio"),
            ("Podcast:Episode?", "Podcast_Episode"),
            ("Episode*1<final>|mix", "Episode_1_final_mix"),
            ("   ...spaced...   ", "spaced")
        ]
        for inp, expected in cases:
            res = AudioPipeline.sanitize_filename(inp)
            self.assertEqual(res, expected, f"Failed sanitizing {inp} -> {res}")

    def test_version_collision_resolution(self):
        """Create ver00, ver01, ver02, ver04: next version must be ver05 (deterministic max+1)."""
        target = self.temp_dir
        base = "interview"
        model = "ZipEnhancer-S"

        for v in (0, 1, 2, 4):
            fname = f"enhanced_{base}_{model}_ver{v:02d}.wav"
            with open(os.path.join(target, fname), "w") as f:
                f.write("test")

        next_path = AudioPipeline.get_versioned_filename(target, base, model_name=model)
        self.assertEqual(os.path.basename(next_path), f"enhanced_{base}_{model}_ver05.wav")

    def test_model_specific_version_counters(self):
        """Different models must have distinct version counters that do not collide."""
        target = self.temp_dir
        base = "voiceover"

        p_mp = AudioPipeline.get_versioned_filename(target, base, model_name="MP-SENet")
        self.assertEqual(os.path.basename(p_mp), "enhanced_voiceover_MP-SENet_ver00.wav")
        with open(p_mp, "w") as f: f.write("mp0")

        # ZipEnhancer on the same audio should still start at ver00
        p_zip = AudioPipeline.get_versioned_filename(target, base, model_name="ZipEnhancer-S")
        self.assertEqual(os.path.basename(p_zip), "enhanced_voiceover_ZipEnhancer-S_ver00.wav")

    def test_audio_numerical_validation(self):
        """Validate finite, not NaN, not Inf, nonzero signal detection."""
        # 1. Normal valid audio
        clean_audio = AudioGenerator.generate_sine_wave(freq_hz=440.0, duration_sec=1.0, sr=16000)
        val = AudioValidator.validate(clean_audio, clean_audio, 16000, 16000)
        self.assertTrue(val["valid"])

        # 2. Corrupt audio with NaN
        nan_audio = clean_audio.copy()
        nan_audio[100] = np.nan
        val_nan = AudioValidator.validate(clean_audio, nan_audio, 16000, 16000)
        self.assertFalse(val_nan["valid"])
        self.assertTrue(any("NaN" in e for e in val_nan["errors"]))

        # 3. Corrupt audio with Inf
        inf_audio = clean_audio.copy()
        inf_audio[200] = np.inf
        val_inf = AudioValidator.validate(clean_audio, inf_audio, 16000, 16000)
        self.assertFalse(val_inf["valid"])
        self.assertTrue(any("inf" in e.lower() for e in val_inf["errors"]))

    def test_audio_resampling_fidelity(self):
        """Test polyphase sinc resampling between 16k, 44.1k, 48k."""
        audio_16k = AudioGenerator.generate_sine_wave(freq_hz=1000.0, duration_sec=1.0, sr=16000)
        audio_48k = AudioPipeline.resample(audio_16k, 16000, 48000)
        self.assertEqual(len(audio_48k), 48000)
        self.assertFalse(np.isnan(audio_48k).any())

        audio_44k = AudioPipeline.resample(audio_48k, 48000, 44100)
        self.assertEqual(len(audio_44k), 44100)
        self.assertFalse(np.isnan(audio_44k).any())

    def test_clipped_audio_limiting_guard(self):
        """Audio exceeding 0 dBFS must be safely limited without clipping corruption."""
        clipped = AudioGenerator.generate_clipped_audio(duration_sec=0.5, sr=16000)
        out_file = os.path.join(self.temp_dir, "limited.wav")
        AudioPipeline.save_wav(out_file, clipped, 16000)

        # Inspect saved file
        import soundfile as sf
        read_back, sr = sf.read(out_file)
        peak = np.max(np.abs(read_back))
        self.assertLessEqual(peak, 1.0)
        self.assertFalse(np.isnan(read_back).any())

if __name__ == "__main__":
    unittest.main()
