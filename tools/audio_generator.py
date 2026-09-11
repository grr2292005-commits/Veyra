import os
import numpy as np
import soundfile as sf
from typing import Tuple

class AudioGenerator:
    """Utility class to generate clean, edge-case, and pathological audio signals for testing."""

    @staticmethod
    def generate_silence(duration_sec: float = 1.0, sr: int = 16000, channels: int = 1) -> np.ndarray:
        samples = int(duration_sec * sr)
        if channels == 1:
            return np.zeros(samples, dtype=np.float32)
        return np.zeros((samples, channels), dtype=np.float32)

    @staticmethod
    def generate_near_silence(duration_sec: float = 1.0, sr: int = 16000, level_db: float = -80.0) -> np.ndarray:
        samples = int(duration_sec * sr)
        amplitude = 10.0 ** (level_db / 20.0)
        noise = (np.random.rand(samples).astype(np.float32) * 2.0 - 1.0) * amplitude
        return noise

    @staticmethod
    def generate_sine_wave(freq_hz: float = 440.0, duration_sec: float = 1.0, sr: int = 16000, amplitude: float = 0.5) -> np.ndarray:
        samples = int(duration_sec * sr)
        t = np.linspace(0, duration_sec, samples, endpoint=False, dtype=np.float32)
        return (np.sin(2.0 * np.pi * freq_hz * t) * amplitude).astype(np.float32)

    @staticmethod
    def generate_clipped_audio(duration_sec: float = 1.0, sr: int = 16000) -> np.ndarray:
        """Generates audio that deliberately clips beyond [-1.0, 1.0]"""
        sine = AudioGenerator.generate_sine_wave(freq_hz=300.0, duration_sec=duration_sec, sr=sr, amplitude=2.5)
        # Saturated hard clip
        return np.clip(sine, -1.5, 1.5).astype(np.float32)

    @staticmethod
    def generate_stereo(duration_sec: float = 1.0, sr: int = 48000) -> np.ndarray:
        samples = int(duration_sec * sr)
        left = AudioGenerator.generate_sine_wave(freq_hz=440.0, duration_sec=duration_sec, sr=sr, amplitude=0.4)
        right = AudioGenerator.generate_sine_wave(freq_hz=880.0, duration_sec=duration_sec, sr=sr, amplitude=0.4)
        return np.stack([left, right], axis=-1)

    @staticmethod
    def generate_speech_like(duration_sec: float = 3.0, sr: int = 16000, rms_target: float = 0.1) -> np.ndarray:
        """Synthesizes speech-like audio with formants (f0=140Hz harmonics) and natural modulated envelope."""
        samples = int(duration_sec * sr)
        t = np.linspace(0, duration_sec, samples, endpoint=False, dtype=np.float32)
        # Formant harmonics: 140Hz, 280Hz, 840Hz, 2200Hz, 3200Hz
        signal = (
            0.5 * np.sin(2.0 * np.pi * 140.0 * t) +
            0.3 * np.sin(2.0 * np.pi * 280.0 * t) +
            0.2 * np.sin(2.0 * np.pi * 840.0 * t) +
            0.1 * np.sin(2.0 * np.pi * 2200.0 * t) +
            0.05 * np.sin(2.0 * np.pi * 3200.0 * t)
        ).astype(np.float32)
        # Add slight background noise (SNR ~ 15dB)
        noise = (np.random.rand(samples).astype(np.float32) * 2.0 - 1.0) * 0.03
        combined = signal + noise
        # Modulation envelope (syllable rate ~ 4 Hz)
        envelope = (0.5 + 0.5 * np.sin(2.0 * np.pi * 4.0 * t)).astype(np.float32)
        combined = combined * envelope
        # Normalize to target RMS
        current_rms = np.sqrt(np.mean(combined ** 2))
        if current_rms > 1e-8:
            combined = combined * (rms_target / current_rms)
        return combined.astype(np.float32)

    @staticmethod
    def generate_impulse(duration_sec: float = 1.0, sr: int = 16000) -> np.ndarray:
        """Generates isolated click/impulse spikes."""
        samples = int(duration_sec * sr)
        audio = np.zeros(samples, dtype=np.float32)
        for idx in [sr // 4, sr // 2, (3 * sr) // 4]:
            if idx < samples:
                audio[idx] = 0.95
        return audio

    @staticmethod
    def save_temp_wav(output_path: str, audio: np.ndarray, sr: int = 16000) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        sf.write(output_path, audio, sr, subtype="PCM_24" if audio.dtype != np.float32 else "FLOAT")
        return output_path

