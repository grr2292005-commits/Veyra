import os
import sys
import json
import torch
import numpy as np
from typing import Dict, Any, Optional, Callable

from .base_adapter import BaseModelAdapter

ARCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "arch", "zipenhancer"))

from .arch.zipenhancer.zipenhancer import ZipenhancerDecorator

class ZipEnhancerAdapter(BaseModelAdapter):
    """
    Adapter for ZipEnhancer-S: Dual-Path Down-Up Sampling Zipformer.
    """
    def __init__(self, model_id: str, model_meta: Dict[str, Any]):
        super().__init__(model_id, model_meta)
        self.decorator = None

    def initialize(self, checkpoint_path: str, device: Optional[str] = None) -> bool:
        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        ckpt_dir = os.path.dirname(checkpoint_path)
        cfg_path = os.path.join(ckpt_dir, "configuration.json")
        if not os.path.exists(cfg_path):
            cfg_path = os.path.join(ARCH_DIR, "configs", "configuration.json")

        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_cfg = cfg.get("model", {})
        else:
            model_cfg = {
                "dense_channel": 64, "num_tsconformers": 4, "batch_first": True, "model_num_spks": 1,
                "former_conf": {
                    "num_encoder_layers": [1, 1, 1, 1], "downsampling_factor": [1, 2, 2, 1],
                    "f_downsampling_factor": [1, 2, 2, 1], "encoder_dim": [64, 64, 64, 64],
                    "pos_dim": 24, "num_heads": 4, "query_head_dim": 12, "pos_head_dim": 4,
                    "value_head_dim": 8, "feedforward_dim": [256, 256, 256, 256],
                    "cnn_module_kernel": 15, "causal": False, "encoder_unmasked_dim": 64,
                    "warmup_batches": 4000.0
                }
            }

        self.decorator = ZipenhancerDecorator(checkpoint_path, **model_cfg)
        self.model = self.decorator.model.to(self.device).eval()

        # Warmup pass
        with torch.no_grad():
            dummy = torch.randn(1, 16000, device=self.device)
            _ = self.decorator.forward({"noisy": dummy})

        if self.device.type == "cuda":
            torch.cuda.synchronize()
        return True

    def is_initialized(self) -> bool:
        return self.decorator is not None and self.model is not None

    def process(
        self,
        audio: np.ndarray,
        sr: int,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> np.ndarray:
        if not self.is_initialized():
            raise RuntimeError("ZipEnhancer-S model not initialized.")

        if sr != 16000:
            raise ValueError(f"ZipEnhancer-S requires 16000 Hz audio, got {sr} Hz.")

        if audio.ndim > 1:
            audio = audio[:, 0]

        input_len = len(audio)
        window_sec = 1.0
        stride_sec = 0.5
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
                tensor_chunk = torch.from_numpy(chunk).float().unsqueeze(0).to(self.device)
                out_chunk = self.decorator.forward({"noisy": tensor_chunk})["wav_l2"][0].detach().cpu().numpy()

                enhanced_accum[idx:idx + win_samples] += out_chunk * hann
                weight_accum[idx:idx + win_samples] += hann
                idx += stride_samples
                chunk_idx += 1

                if progress_cb:
                    pct = min(99.0, (chunk_idx / total_chunks) * 100.0)
                    progress_cb(pct, f"Enhancing audio with ZipEnhancer-S ({pct:.0f}%)...")

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
        self.decorator = None
        self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
