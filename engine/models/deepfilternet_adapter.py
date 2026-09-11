import os
import torch
import numpy as np
from typing import Dict, Any, Optional, Callable

from .base_adapter import BaseModelAdapter

class DeepFilterNetAdapter(BaseModelAdapter):
    """
    Adapter for DeepFilterNet3: Low-latency, fullband 48 kHz CPU/GPU speech enhancement.
    """
    def __init__(self, model_id: str, model_meta: Dict[str, Any]):
        super().__init__(model_id, model_meta)
        self.df_state = None

    def initialize(self, checkpoint_path: str, device: Optional[str] = None) -> bool:
        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        try:
            from df.enhance import init_df
            from df.config import config

            ckpt_dir = os.path.dirname(checkpoint_path)
            if os.path.isfile(checkpoint_path):
                self.model, self.df_state, _ = init_df()
            else:
                self.model, self.df_state, _ = init_df(model_base_dir=ckpt_dir)

            dev_str = "cuda:0" if self.device.type == "cuda" else "cpu"
            config.set("DEVICE", dev_str, str, section="train")
            self.model = self.model.to(self.device).eval()
            return True
        except ImportError as err:
            raise RuntimeError(
                "DeepFilterNet3 runtime component is missing or damaged. "
                "Please run Speechify installer to repair."
            ) from err

    def is_initialized(self) -> bool:
        return self.model is not None and self.df_state is not None

    def process(
        self,
        audio: np.ndarray,
        sr: int,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> np.ndarray:
        if not self.is_initialized():
            raise RuntimeError("DeepFilterNet3 model not initialized.")

        if sr != 48000:
            raise ValueError(f"DeepFilterNet3 operates at 48000 Hz, got {sr} Hz.")

        if audio.ndim > 1:
            audio = audio[:, 0]

        input_len = len(audio)

        if cancel_check and cancel_check():
            raise InterruptedError("Processing cancelled by user.")

        if progress_cb:
            progress_cb(15.0, "Running DeepFilterNet3 fullband enhancement...")

        from df.enhance import enhance

        # DeepFilterNet expects [1, T] CPU tensor for Rust feature analysis
        audio_tensor = torch.from_numpy(audio).float().unsqueeze(0).cpu()

        with torch.no_grad():
            enhanced_tensor = enhance(self.model, self.df_state, audio_tensor)
            if cancel_check and cancel_check():
                raise InterruptedError("Processing cancelled by user.")

        enhanced = enhanced_tensor.squeeze(0).detach().cpu().numpy()

        if len(enhanced) > input_len:
            enhanced = enhanced[:input_len]
        elif len(enhanced) < input_len:
            enhanced = np.pad(enhanced, (0, input_len - len(enhanced)))

        peak = np.max(np.abs(enhanced))
        if peak > 1.0:
            enhanced = enhanced / (peak + 1e-6)

        if progress_cb:
            progress_cb(100.0, "Enhancement complete.")

        return enhanced.astype(np.float32)

    def cleanup(self):
        self.model = None
        self.df_state = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
