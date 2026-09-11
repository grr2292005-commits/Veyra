import os
import sys
import time
import numpy as np
import soundfile as sf
from typing import Dict, Any, Optional, Callable

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline
from engine.validation.audio_validator import AudioValidator
from engine.hardware.detector import HardwareDetector
from engine.models.factory import ModelFactory
from models.manager import ModelManager

class EnhancementJob:
    def __init__(
        self,
        job_id: str,
        source_file: str,
        clip_name: Optional[str] = None,
        track_index: Optional[int] = None,
        track_name: Optional[str] = None,
        in_point_sec: Optional[float] = None,
        out_point_sec: Optional[float] = None,
        sequence_sr: int = 48000,
        model_id: str = "mp_senet",
        device: str = "auto",
        output_dir: Optional[str] = None,
        job_dir: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None
    ):
        self.job_id = job_id
        self.source_file = source_file
        self.clip_name = clip_name
        self.track_index = track_index
        self.track_name = track_name or (metadata.get("track_name") if metadata else None)
        self.in_point_sec = in_point_sec
        self.out_point_sec = out_point_sec
        self.sequence_sr = sequence_sr
        self.model_id = model_id
        self.device = device or "auto"
        self.output_dir = output_dir
        self.job_dir = job_dir
        self.metadata = metadata or {}
        self.settings = settings or {}

        self.status = "queued"
        self.progress_pct = 0.0
        self.progress_msg = "Queued..."
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.cancelled = False

class EnhancementOrchestrator:
    """
    Coordinates the complete end-to-end local speech enhancement workflow:
    extraction -> resampling -> inference -> reconstruction -> validation -> broadcast output.
    """
    def __init__(self, model_manager: Optional[ModelManager] = None):
        self.model_manager = model_manager or ModelManager()
        self.hardware_detector = HardwareDetector()

    def run_job(
        self,
        job: EnhancementJob,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        t_start = time.perf_counter()
        job.status = "running"

        def _report(pct: float, msg: str):
            job.progress_pct = pct
            job.progress_msg = msg
            if progress_cb:
                progress_cb(pct, msg)

        def _cancel_check() -> bool:
            return job.cancelled

        # 1. Source verification
        if not os.path.isfile(job.source_file):
            raise FileNotFoundError(f"Source media file not found: {job.source_file}")

        _report(5.0, "Inspecting audio stream...")
        info = AudioPipeline.inspect_audio(job.source_file)
        orig_sr = info["sample_rate"]

        # 2. Extract exact sub-segment at source sample rate
        _report(10.0, "Extracting target timeline segment...")
        raw_audio, extracted_sr, actual_in, actual_dur = AudioPipeline.load_audio_range(
            job.source_file, in_sec=job.in_point_sec, out_sec=job.out_point_sec
        )
        if _cancel_check():
            raise InterruptedError("Cancelled.")

        # Convert to mono for model inference if stereo
        if raw_audio.ndim > 1:
            mono_audio = np.mean(raw_audio, axis=1).astype(np.float32)
        else:
            mono_audio = raw_audio.astype(np.float32)

        # Standardize source to sequence_sr if needed
        target_seq_sr = job.sequence_sr or 48000
        if extracted_sr != target_seq_sr:
            ref_audio = AudioPipeline.resample(mono_audio, extracted_sr, target_seq_sr)
        else:
            ref_audio = mono_audio
        ref_samples = len(ref_audio)

        # 3. Model setup
        model_meta = self.model_manager.registry_data["models"].get(job.model_id)
        if not model_meta:
            raise ValueError(f"Unknown model ID: {job.model_id}")

        ckpt_path = self.model_manager.get_model_file_path(job.model_id)
        if not ckpt_path or not os.path.exists(ckpt_path):
            raise RuntimeError(
                f"Model '{model_meta['name']}' is not installed yet. "
                "Please download it in the Models panel first."
            )

        # Determine execution device
        # Determine execution device
        req_dev = (job.device or "auto").lower()
        if req_dev == "cpu":
            target_device = "cpu"
        elif req_dev in ("cuda", "gpu") or req_dev.startswith("cuda"):
            try:
                import torch
                if not torch.cuda.is_available():
                    raise RuntimeError("GPU processing was requested, but CUDA is not available on this system. Please select CPU or Automatic.")
                target_device = req_dev if req_dev.startswith("cuda:") else "cuda:0"
                # Validate CUDA device allocation
                t = torch.zeros((1,), device=target_device)
                del t
            except Exception as cuda_ex:
                raise RuntimeError(f"GPU device selection failed: {str(cuda_ex)}")
        else:  # auto
            try:
                import torch
                target_device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except Exception:
                target_device = "cpu"

        # Pre-flight VRAM safety validation
        if target_device.startswith("cuda"):
            try:
                import torch
                dev_idx = int(target_device.split(":")[1]) if ":" in target_device else 0
                free_b, total_b = torch.cuda.mem_get_info(dev_idx)
                free_mb = free_b / (1024 ** 2)
                vram_reqs = {
                    "mossformergan": 3500,
                    "mp_senet": 700,
                    "zipenhancer": 500,
                    "deepfilternet3": 200
                }
                needed_mb = vram_reqs.get(job.model_id, 400)
                if free_mb < needed_mb:
                    torch.cuda.empty_cache()
                    free_b, _ = torch.cuda.mem_get_info(dev_idx)
                    free_mb = free_b / (1024 ** 2)
                    if free_mb < (needed_mb * 0.65):
                        raise RuntimeError(
                            f"Insufficient GPU VRAM to run {model_meta['name']} "
                            f"(Available: {free_mb:.0f} MB, Required: ~{needed_mb} MB). "
                            "Please select CPU or a balanced model such as ZipEnhancer-S."
                        )
            except Exception as mem_ex:
                if isinstance(mem_ex, RuntimeError):
                    raise

        _report(15.0, f"Loading {model_meta['name']} model weights ({target_device})...")
        adapter = ModelFactory.get_adapter(job.model_id, model_meta, ckpt_path, device=target_device)

        model_native_sr = model_meta.get("sample_rate_hz", 16000)

        # 4. Resample to model native sample rate
        if target_seq_sr != model_native_sr:
            _report(20.0, f"Resampling audio to model native rate ({model_native_sr} Hz)...")
            model_input_audio = AudioPipeline.resample(ref_audio, target_seq_sr, model_native_sr)
        else:
            model_input_audio = ref_audio

        # 5. Process through model adapter with chunk progress
        def _adapter_progress(pct: float, msg: str):
            # Scale adapter progress to 25% -> 85%
            scaled_pct = 25.0 + (pct / 100.0) * 60.0
            _report(scaled_pct, msg)

        _report(25.0, f"Enhancing audio with {model_meta['name']}...")
        t_infer_start = time.perf_counter()
        enhanced_native = adapter.process(
            model_input_audio,
            sr=model_native_sr,
            progress_cb=_adapter_progress,
            cancel_check=_cancel_check
        )
        t_infer_elapsed = time.perf_counter() - t_infer_start

        if _cancel_check():
            raise InterruptedError("Cancelled.")

        # 6. Reconstruct to sequence sample rate (e.g. 48kHz broadcast audio)
        _report(85.0, f"Reconstructing broadcast audio ({target_seq_sr} Hz)...")
        if model_native_sr != target_seq_sr:
            enhanced_final = AudioPipeline.resample(enhanced_native, model_native_sr, target_seq_sr)
        else:
            enhanced_final = enhanced_native

        # Guarantee exact sample alignment matching input length
        if len(enhanced_final) > ref_samples:
            enhanced_final = enhanced_final[:ref_samples]
        elif len(enhanced_final) < ref_samples:
            enhanced_final = np.pad(enhanced_final, (0, ref_samples - len(enhanced_final)))

        # 7. Timeline & Audio Validation
        _report(92.0, "Validating audio integrity and duration...")
        validation = AudioValidator.validate(
            input_audio=ref_audio,
            output_audio=enhanced_final,
            input_sr=target_seq_sr,
            output_sr=target_seq_sr
        )

        if not validation["valid"]:
            error_details = "; ".join(validation["errors"])
            raise ValueError(f"Audio validation failed: {error_details}")

        # 8. Determine destination folder and versioned filename
        base_name = job.clip_name or os.path.basename(job.source_file)
        if not job.output_dir:
            src_dir = os.path.dirname(os.path.abspath(job.source_file))
            target_dir = os.path.join(src_dir, "SpeechEnhancer", "Enhanced Audio")
        else:
            target_dir = job.output_dir

        disambiguator = job.settings.get("disambiguator") or job.track_name or (job.metadata.get("track_name") if job.metadata else None)
        out_wav_path = AudioPipeline.get_versioned_filename(
            target_dir,
            base_name,
            model_name=model_meta.get("name", job.model_id),
            disambiguator=disambiguator
        )

        t_write_start = time.perf_counter()
        _report(96.0, f"Writing broadcast WAV to disk...")
        AudioPipeline.save_wav(out_wav_path, enhanced_final, target_seq_sr, subtype="PCM_24")
        t_write_elapsed = time.perf_counter() - t_write_start

        # Verify output WAV directly on disk
        t_val_start = time.perf_counter()
        if not os.path.isfile(out_wav_path) or os.path.getsize(out_wav_path) < 44:
            raise FileNotFoundError(f"Generated WAV file is invalid or empty on disk: {out_wav_path}")

        out_info = sf.info(out_wav_path)
        if out_info.frames == 0 or out_info.duration == 0:
            raise ValueError(f"Generated WAV file has 0 audio frames: {out_wav_path}")

        # Compute definitive source and output signal metrics
        src_rms = float(np.sqrt(np.mean(ref_audio ** 2))) if len(ref_audio) > 0 else 0.0
        src_peak = float(np.max(np.abs(ref_audio))) if len(ref_audio) > 0 else 0.0
        out_rms = float(np.sqrt(np.mean(enhanced_final ** 2))) if len(enhanced_final) > 0 else 0.0
        out_peak = float(np.max(np.abs(enhanced_final))) if len(enhanced_final) > 0 else 0.0

        if src_rms > 1e-5 and out_rms < 1e-6:
            raise ValueError("Enhanced output audio collapsed to silence while source contains active audio.")

        t_val_elapsed = time.perf_counter() - t_val_start

        audio_diagnostics = {
            "source": {
                "duration_sec": round(len(ref_audio) / target_seq_sr, 4),
                "rms": round(src_rms, 6),
                "peak": round(src_peak, 6),
                "sample_rate": target_seq_sr,
                "channels": 1
            },
            "output": {
                "duration_sec": round(len(enhanced_final) / target_seq_sr, 4),
                "rms": round(out_rms, 6),
                "peak": round(out_peak, 6),
                "sample_rate": target_seq_sr,
                "channels": out_info.channels
            }
        }

        t_elapsed = time.perf_counter() - t_start
        _report(100.0, "Complete.")

        timing_ms = {
            "inference_ms": round(t_infer_elapsed * 1000, 1),
            "wav_writing_ms": round(t_write_elapsed * 1000, 1),
            "validation_ms": round(t_val_elapsed * 1000, 1),
            "total_engine_ms": round(t_elapsed * 1000, 1)
        }

        result = {
            "job_id": job.job_id,
            "status": "completed",
            "model_id": job.model_id,
            "model_name": model_meta["name"],
            "clip_name": job.clip_name or base_name,
            "track_index": job.track_index,
            "track_name": job.track_name or (job.metadata.get("track_name") if job.metadata else None),
            "device": str(getattr(adapter, "device", target_device)),
            "source_file": job.source_file,
            "output_file": os.path.abspath(out_wav_path),
            "enhanced_file": os.path.abspath(out_wav_path),
            "output_filename": os.path.basename(out_wav_path),
            "target_dir": os.path.abspath(target_dir),
            "in_point_sec": actual_in,
            "duration_sec": actual_dur,
            "sample_rate": target_seq_sr,
            "samples": len(enhanced_final),
            "inference_time_sec": round(t_infer_elapsed, 3),
            "processing_time_sec": round(t_elapsed, 3),
            "real_time_factor_rtf": round(t_infer_elapsed / actual_dur, 4) if actual_dur > 0 else 0.0,
            "speed_multiplier": f"{actual_dur / t_infer_elapsed:.1f}x" if t_infer_elapsed > 0 else "N/A",
            "validation": validation["metrics"],
            "audio_diagnostics": audio_diagnostics,
            "timing_ms": timing_ms
        }

        if job.job_dir and os.path.isdir(job.job_dir):
            try:
                import json
                # Write output.wav copy directly into job_dir for complete per-track isolation
                job_out_wav = os.path.join(job.job_dir, "output.wav")
                if not os.path.exists(job_out_wav):
                    AudioPipeline.save_wav(job_out_wav, enhanced_final, target_seq_sr, subtype="PCM_24")
                with open(os.path.join(job.job_dir, "output.json"), "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)
                if job.track_name:
                    safe_t = AudioPipeline.sanitize_filename(job.track_name)
                    with open(os.path.join(job.job_dir, f"{safe_t}_output.json"), "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2)
            except Exception:
                pass

        job.status = "completed"
        job.result = result
        return result
