import os
import sys
import tempfile
import soundfile as sf
import numpy as np
import torch
from typing import Dict, Any, Optional, Callable

from .base_adapter import BaseModelAdapter

class MossFormerGANAdapter(BaseModelAdapter):
    """
    Adapter for MossFormerGAN-SE: Dual-Decoder Adversarial Speech Enhancement.
    """
    def __init__(self, model_id: str, model_meta: Dict[str, Any]):
        super().__init__(model_id, model_meta)
        self.clearvoice_instance = None

    def initialize(self, checkpoint_path: str, device: Optional[str] = None) -> bool:
        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        # 1. Resolve private runtime dependencies
        try:
            from clearvoice import ClearVoice
        except ImportError:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            candidates = [
                os.path.join(base_dir, "runtime", "Lib", "site-packages"),
                os.path.join(sys.prefix, "Lib", "site-packages")
            ]
            for cand in candidates:
                if os.path.isdir(cand) and cand not in sys.path:
                    sys.path.insert(0, cand)
            try:
                from clearvoice import ClearVoice
            except ImportError as err:
                raise RuntimeError(
                    "MossFormerGAN-SE model runtime could not be loaded. "
                    "The private engine components may be damaged."
                ) from err

        # 2. Ensure local checkpoint files exist so ClearVoice never attempts unneeded downloads
        ckpt_target_dir = os.path.abspath("checkpoints/MossFormerGAN_SE_16K")
        os.makedirs(ckpt_target_dir, exist_ok=True)
        flag_file = os.path.join(ckpt_target_dir, "last_best_checkpoint")
        pt_file = os.path.join(ckpt_target_dir, "last_best_checkpoint.pt")
        if not os.path.isfile(flag_file):
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write("last_best_checkpoint.pt\n")
        if not os.path.isfile(pt_file) and os.path.isfile(checkpoint_path):
            try:
                import shutil
                shutil.copy2(checkpoint_path, pt_file)
            except Exception:
                pass

        try:
            self.clearvoice_instance = ClearVoice(
                task="speech_enhancement",
                model_names=["MossFormerGAN_SE_16K"]
            )
            return True
        except Exception as ex:
            raise RuntimeError(f"Failed to initialize MossFormerGAN-SE: {str(ex)}") from ex

    def is_initialized(self) -> bool:
        return self.clearvoice_instance is not None

    def process(
        self,
        audio: np.ndarray,
        sr: int,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> np.ndarray:
        if not self.is_initialized():
            raise RuntimeError("MossFormerGAN-SE model not initialized.")

        if sr != 16000:
            raise ValueError(f"MossFormerGAN-SE requires 16000 Hz audio, got {sr} Hz.")

        if audio.ndim > 1:
            audio = audio[:, 0]

        input_len = len(audio)

        if cancel_check and cancel_check():
            raise InterruptedError("Processing cancelled by user.")

        if progress_cb:
            progress_cb(10.0, "Running MossFormerGAN-SE inference...")

        # ClearVoice operates on an audio file or in-memory path
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            tmp_in_path = tmp_in.name
            sf.write(tmp_in_path, audio, sr, subtype="FLOAT")

        try:
            enhanced = self.clearvoice_instance(input_path=tmp_in_path, online_write=False)
            if cancel_check and cancel_check():
                raise InterruptedError("Processing cancelled by user.")
        finally:
            if os.path.exists(tmp_in_path):
                try:
                    os.remove(tmp_in_path)
                except Exception:
                    pass

        # Handle output format
        if isinstance(enhanced, dict):
            k = list(enhanced.keys())[0]
            enhanced = enhanced[k]
        enhanced = np.asarray(enhanced, dtype=np.float32).flatten()

        # Match exact input duration
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
        self.clearvoice_instance = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
