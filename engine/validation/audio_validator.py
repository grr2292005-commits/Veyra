import numpy as np
from typing import Dict, Any, List, Optional

class AudioValidationError(ValueError):
    """Raised when enhanced audio fails critical timeline or signal integrity criteria."""
    pass

class AudioValidator:
    """
    Guarantees that enhanced audio files meet strict broadcast timeline criteria
    before they are ever imported into Adobe Premiere Pro.
    """

    MAX_DURATION_TOLERANCE_SEC = 0.045  # ~1 video frame at 24fps (~42ms)
    MAX_PERMITTED_PEAK = 1.0001
    MIN_EXPECTED_RMS = 1e-6  # -120 dBFS

    def __init__(self, max_duration_drift_ms: float = 45.0):
        self.max_duration_tolerance_sec = max_duration_drift_ms / 1000.0

    @classmethod
    def validate(
        cls,
        input_audio: np.ndarray,
        output_audio: np.ndarray,
        input_sr: int,
        output_sr: int,
        max_duration_drift_ms: Optional[float] = None,
        raise_on_error: bool = False
    ) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        max_dur_sec = (max_duration_drift_ms / 1000.0) if max_duration_drift_ms is not None else cls.MAX_DURATION_TOLERANCE_SEC

        # 1. NaN and Inf check
        if np.isnan(output_audio).any():
            errors.append("Output audio contains NaN (Not a Number) floating-point errors.")
        if np.isinf(output_audio).any():
            errors.append("Output audio contains infinite floating-point values.")

        # 2. Duration and Sample-length validation
        in_dur = len(input_audio) / input_sr
        out_dur = len(output_audio) / output_sr
        dur_diff = abs(out_dur - in_dur)

        if dur_diff > max_dur_sec:
            errors.append(
                f"Audio duration mismatch: Input={in_dur:.4f}s, Output={out_dur:.4f}s. "
                f"Difference of {dur_diff*1000:.1f}ms exceeds timeline tolerance ({max_dur_sec*1000:.1f}ms)."
            )

        # 3. Peak and Clipping Validation
        peak = float(np.max(np.abs(output_audio))) if len(output_audio) > 0 else 0.0
        has_clipping = False
        if peak > cls.MAX_PERMITTED_PEAK:
            has_clipping = True
            warnings.append(f"Output peak ({peak:.4f}) exceeded 0.0 dBFS and was normalized to prevent clipping.")

        # 4. Silence / Drop-out Validation
        rms = float(np.sqrt(np.mean(output_audio ** 2))) if len(output_audio) > 0 else 0.0
        in_rms = float(np.sqrt(np.mean(input_audio ** 2))) if len(input_audio) > 0 else 0.0

        if rms < cls.MIN_EXPECTED_RMS and in_rms > cls.MIN_EXPECTED_RMS * 10:
            errors.append("Output audio is completely silent or collapsed to zero energy.")

        # 5. Dynamic Range & Crest Factor
        crest_factor_db = 20 * np.log10(peak / (rms + 1e-9)) if rms > 0 else 0.0

        metrics = {
            "input_duration_sec": in_dur,
            "output_duration_sec": out_dur,
            "duration_difference_ms": dur_diff * 1000.0,
            "duration_drift_ms": dur_diff * 1000.0,
            "peak_amplitude": peak,
            "peak_dbfs": float(20 * np.log10(peak + 1e-9)),
            "rms_level": rms,
            "rms_dbfs": float(20 * np.log10(rms + 1e-9)),
            "crest_factor_db": float(crest_factor_db),
            "has_clipping": has_clipping
        }

        is_valid = (len(errors) == 0)

        if not is_valid and raise_on_error:
            raise AudioValidationError("; ".join(errors))

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "metrics": metrics,
            "duration_drift_ms": dur_diff * 1000.0,
            "has_clipping": has_clipping
        }
