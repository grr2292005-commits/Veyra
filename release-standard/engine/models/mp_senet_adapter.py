import os
import sys
import json
import time
import torch
import numpy as np
from typing import Dict, Any, Optional, Callable

from .base_adapter import BaseModelAdapter

# Append architecture path
ARCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "arch", "mp_senet"))
if ARCH_DIR not in sys.path:
    sys.path.insert(0, ARCH_DIR)

from env import AttrDict
from dataset import mag_pha_stft, mag_pha_istft
from model import MPNet

class MPSENetAdapter(BaseModelAdapter):
    """
    Adapter for MP-SENet: Explicit Parallel Magnitude and Phase Estimation.
    """
    def __init__(self, model_id: str, model_meta: Dict[str, Any]):
        super().__init__(model_id, model_meta)
        self.config = None

    def initialize(self, checkpoint_path: str, device: Optional[str] = None) -> bool:
        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        # Look for config.json in checkpoint directory or storage
        ckpt_dir = os.path.dirname(checkpoint_path)
        cfg_path = os.path.join(ckpt_dir, "config.json")
        if not os.path.exists(cfg_path):
            # Fallback default configuration
            cfg = {
                "dense_channel": 64, "compress_factor": 0.3, "num_tsconformers": 4,
                "sampling_rate": 16000, "segment_size": 32000,
                "n_fft": 400, "hop_size": 100, "win_size": 400
            }
        else:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

        self.config = AttrDict(cfg)
        self.model = MPNet(self.config).to(self.device).eval()

        ckpt = torch.load(checkpoint_path, map_location=self.device)
        state_dict = ckpt.get("generator", ckpt)
        self.model.load_state_dict(state_dict)

        # Warmup pass
        with torch.no_grad():
            dummy = torch.randn(1, int(self.config.sampling_rate * 1.0), device=self.device)
            noisy_amp, noisy_pha, _ = mag_pha_stft(
                dummy, self.config.n_fft, self.config.hop_size, self.config.win_size, self.config.compress_factor
            )
            amp_g, pha_g, _ = self.model(noisy_amp, noisy_pha)
            _ = mag_pha_istft(amp_g, pha_g, self.config.n_fft, self.config.hop_size, self.config.win_size, self.config.compress_factor)
        
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        return True

    def is_initialized(self) -> bool:
        return self.model is not None

    def process(
        self,
        audio: np.ndarray,
        sr: int,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> np.ndarray:
        if not self.is_initialized():
            raise RuntimeError("MP-SENet model not initialized.")

        if sr != 16000:
            raise ValueError(f"MP-SENet requires 16000 Hz audio, got {sr} Hz.")

        if audio.ndim > 1:
            audio = audio[:, 0]

        input_len = len(audio)
        window_sec = 2.0
        stride_sec = 1.0
        win_samples = int(sr * window_sec)
        stride_samples = int(sr * stride_sec)
        hann = np.hanning(win_samples).astype(np.float32)

        pad_needed = (stride_samples - (input_len - win_samples) % stride_samples) % stride_samples
        if input_len < win_samples:
            pad_needed = win_samples - input_len
        padded_audio = np.pad(audio, (0, pad_needed + win_samples), mode="constant")

        enhanced_accum = np.zeros(len(padded_audio), dtype=np.float32)
        weight_accum = np.zeros(len(padded_audio), dtype=np.float32)

        total_chunks = max(1, (len(padded_audio) - win_samples) // stride_samples + 1)
        chunk_idx = 0

        with torch.no_grad():
            idx = 0
            while idx + win_samples <= len(padded_audio):
                if cancel_check and cancel_check():
                    raise InterruptedError("Processing cancelled by user.")

                chunk = padded_audio[idx:idx + win_samples]
                tensor_chunk = torch.FloatTensor(chunk).to(self.device)
                energy = torch.sum(tensor_chunk ** 2.0)
                
                if energy < 1e-12:
                    out_chunk = np.zeros_like(chunk)
                else:
                    norm_factor = torch.sqrt(len(tensor_chunk) / energy)
                    normed_chunk = (tensor_chunk * norm_factor).unsqueeze(0)
                    noisy_amp, noisy_pha, _ = mag_pha_stft(
                        normed_chunk, self.config.n_fft, self.config.hop_size, self.config.win_size, self.config.compress_factor
                    )
                    amp_g, pha_g, _ = self.model(noisy_amp, noisy_pha)
                    audio_g = mag_pha_istft(
                        amp_g, pha_g, self.config.n_fft, self.config.hop_size, self.config.win_size, self.config.compress_factor
                    )
                    out_chunk = (audio_g / norm_factor).squeeze().detach().cpu().numpy()

                enhanced_accum[idx:idx + win_samples] += out_chunk * hann
                weight_accum[idx:idx + win_samples] += hann
                idx += stride_samples
                chunk_idx += 1

                if progress_cb:
                    pct = min(99.0, (chunk_idx / total_chunks) * 100.0)
                    progress_cb(pct, f"Enhancing audio with MP-SENet ({pct:.0f}%)...")

        # Normalize overlap-add
        enhanced = enhanced_accum / np.maximum(weight_accum, 1e-8)
        enhanced = enhanced[:input_len]

        peak = np.max(np.abs(enhanced))
        if peak > 1.0:
            enhanced = enhanced / (peak + 1e-6)

        if progress_cb:
            progress_cb(100.0, "Enhancement complete.")

        return enhanced.astype(np.float32)

    def cleanup(self):
        self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
