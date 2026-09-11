from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any, Optional, Callable

class BaseModelAdapter(ABC):
    """
    Abstract Model Adapter defining the unified contract for speech enhancement backends.
    """
    def __init__(self, model_id: str, model_meta: Dict[str, Any]):
        self.model_id = model_id
        self.meta = model_meta
        self.model = None
        self.device = None
        self._is_cancelled = False

    @abstractmethod
    def initialize(self, checkpoint_path: str, device: Optional[str] = None) -> bool:
        """Loads weights and prepares the model on device (cuda / cpu)."""
        pass

    @abstractmethod
    def is_initialized(self) -> bool:
        """Returns True if weights are loaded in memory."""
        pass

    @abstractmethod
    def process(
        self,
        audio: np.ndarray,
        sr: int,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> np.ndarray:
        """
        Processes audio array and returns enhanced audio array.
        Audio input must match the model's native sample rate and channel format.
        """
        pass

    def estimate_processing_time(self, duration_sec: float, has_gpu: bool = True) -> float:
        """Estimates processing duration in seconds based on verified benchmark RTF."""
        rtf = self.meta.get("local_benchmarks_rtx_4050", {}).get("rtf", 0.2)
        if not has_gpu:
            rtf = rtf * 4.0 # Estimate CPU processing factor
        return duration_sec * rtf

    def cancel(self):
        self._is_cancelled = True

    def load(self, checkpoint_path: Optional[str] = None, device: Optional[str] = None):
        if not self.is_initialized():
            self.initialize(checkpoint_path or self.meta.get("path", ""), device=device)

    def enhance(self, audio: np.ndarray, sr: int, **kwargs) -> np.ndarray:
        return self.process(audio, sr, **kwargs)

    def self_test(self, checkpoint_path: str, device: Optional[str] = None) -> Dict[str, Any]:
        """
        Lightweight model runtime validation (Section 31):
        1. Loads checkpoint on specified device.
        2. Generates 0.5s synthetic sample at model native sample rate.
        3. Verifies output is 100% finite (no NaN, no Inf).
        4. Verifies output shape and duration.
        5. Cleans up resources.
        """
        try:
            if not self.is_initialized():
                self.initialize(checkpoint_path, device=device)
            sr = self.meta.get("sample_rate_hz", 16000)
            n_samples = int(sr * 0.5)
            t = np.linspace(0, 0.5, n_samples, endpoint=False)
            synthetic = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.05 * np.random.randn(n_samples)).astype(np.float32)

            enhanced = self.process(synthetic, sr=sr)
            if not np.isfinite(enhanced).all():
                return {
                    "success": False,
                    "status": "Needs attention",
                    "error": "Output contains non-finite floating-point values."
                }
            if len(enhanced) != n_samples:
                return {
                    "success": False,
                    "status": "Needs attention",
                    "error": f"Output length mismatch: expected {n_samples}, got {len(enhanced)}"
                }
            return {
                "success": True,
                "status": "Ready",
                "samples_processed": n_samples,
                "device": str(self.device)
            }
        except Exception as e:
            return {
                "success": False,
                "status": "Needs attention",
                "error": str(e)
            }
        finally:
            self.cleanup()

    @abstractmethod
    def cleanup(self):
        """Frees model tensors and empties GPU cache."""
        pass

