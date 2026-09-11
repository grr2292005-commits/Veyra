import os
import math
import numpy as np
import soundfile as sf
import scipy.signal
from typing import Tuple, Dict, Any, Optional

class AudioPipeline:
    """
    High-fidelity audio extraction, resampling, duration preservation,
    and broadcast WAV synthesis for Premiere Pro timeline integration.
    """

    @staticmethod
    def inspect_audio(file_path: str) -> Dict[str, Any]:
        info = sf.info(file_path)
        return {
            "file_path": file_path,
            "duration_sec": info.duration,
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "frames": info.frames,
            "format": info.format,
            "subtype": info.subtype
        }

    @staticmethod
    def load_audio_range(
        file_path: str,
        in_sec: Optional[float] = None,
        out_sec: Optional[float] = None,
        target_sr: Optional[int] = None
    ) -> Tuple[np.ndarray, int, float, float]:
        """
        Extracts a sample-accurate sub-segment from an audio file.
        Returns: (audio_array, sample_rate, actual_in_sec, actual_duration_sec)
        """
        info = sf.info(file_path)
        sr = info.samplerate
        total_frames = info.frames

        start_frame = 0
        if in_sec is not None and in_sec > 0:
            start_frame = min(int(round(in_sec * sr)), total_frames)

        end_frame = total_frames
        if out_sec is not None and out_sec > in_sec if in_sec is not None else 0:
            end_frame = min(int(round(out_sec * sr)), total_frames)

        frames_to_read = max(0, end_frame - start_frame)
        if frames_to_read == 0:
            raise ValueError(f"Invalid range: in={in_sec}, out={out_sec}, total_duration={info.duration}")

        # Read specific frame slice with soundfile, fallback to torchaudio/librosa if unsupported format
        try:
            data, file_sr = sf.read(file_path, start=start_frame, stop=end_frame, dtype='float32', always_2d=False)
        except Exception as sf_err:
            try:
                import torchaudio
                waveform, file_sr = torchaudio.load(file_path)
                data = waveform.numpy().T
                data = data[start_frame:end_frame]
            except Exception as fallback_err:
                raise ValueError(f"Could not load audio from {file_path}: soundfile error ({sf_err}), fallback error ({fallback_err})")

        # Convert stereo to mono for 1-channel models if needed
        is_stereo = (data.ndim > 1 and data.shape[1] > 1)

        # High-quality sinc resampling if requested
        if target_sr is not None and target_sr != file_sr:
            data = AudioPipeline.resample(data, file_sr, target_sr)
            effective_sr = target_sr
        else:
            effective_sr = file_sr

        actual_in = start_frame / file_sr
        actual_dur = frames_to_read / file_sr

        return data, effective_sr, actual_in, actual_dur

    @staticmethod
    def validate_audio_signal(file_path: str, min_rms: float = 1e-5) -> Dict[str, Any]:
        """
        Calculates signal metrics (duration, sr, channels, rms, peak, finite count)
        and verifies the audio is non-silent and structurally valid.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        file_size = os.path.getsize(file_path)
        if file_size < 44:
            raise ValueError(f"Audio file {file_path} is truncated ({file_size} bytes)")

        info = sf.info(file_path)
        if info.frames == 0:
            raise ValueError(f"Audio file {file_path} contains 0 frames")

        data, sr = sf.read(file_path, dtype='float32', always_2d=False)
        if data.ndim > 1:
            mono = np.mean(data, axis=1)
        else:
            mono = data

        is_finite = bool(np.all(np.isfinite(mono)))
        if not is_finite:
            raise ValueError(f"Audio file {file_path} contains NaN or Inf samples")

        rms = float(np.sqrt(np.mean(mono ** 2.0))) if len(mono) > 0 else 0.0
        peak = float(np.max(np.abs(mono))) if len(mono) > 0 else 0.0

        return {
            "valid": True,
            "duration_sec": float(info.duration),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "frames": int(info.frames),
            "rms": rms,
            "peak": peak,
            "is_finite": is_finite,
            "file_size": file_size,
            "has_signal": bool(rms >= min_rms)
        }

    @staticmethod
    def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        High-quality polyphase sinc resampling via scipy.signal.resample_poly.
        """
        if orig_sr == target_sr:
            return audio.astype(np.float32)

        gcd = math.gcd(orig_sr, target_sr)
        up = target_sr // gcd
        down = orig_sr // gcd

        if audio.ndim == 1:
            resampled = scipy.signal.resample_poly(audio, up, down)
        else:
            channels = [scipy.signal.resample_poly(audio[:, c], up, down) for c in range(audio.shape[1])]
            resampled = np.stack(channels, axis=-1)

        return resampled.astype(np.float32)

    @staticmethod
    def save_wav(
        output_path: str,
        audio: np.ndarray,
        sr: int,
        subtype: str = "PCM_24"
    ) -> str:
        """
        Writes standard uncompressed WAV file (PCM_24 or FLOAT).
        Guards against digital overs (+0 dBFS) by gentle limiting.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        peak = np.max(np.abs(audio))
        if peak > 1.0:
            audio = audio / (peak + 1e-6)

        sf.write(output_path, audio, sr, subtype=subtype)
        return output_path

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """
        Sanitizes a string to be a safe Windows filename while preserving readability.
        Replaces characters: \\ / : * ? " < > | with _
        Handles Unicode, strips extensions, and prevents illegal names.
        """
        import re
        if not name:
            return "audio_clip"
        name_str = str(name).strip()
        # Strip extension if passed e.g. .mp3, .wav
        name_no_ext = os.path.splitext(name_str)[0]
        # Replace illegal Windows characters
        clean = re.sub(r'[\\/*?:"<>|]', '_', name_no_ext)
        # Neutralize any directory traversal sequences (e.g. .. or ...)
        clean = re.sub(r'\.{2,}', '_', clean)
        # Collapse repeated underscores and strip leading/trailing spaces, dots, underscores
        clean = re.sub(r'_+', '_', clean).strip('_ .')
        return clean or "audio_clip"

    @staticmethod
    def sanitize_model_name(name: str) -> str:
        """Sanitizes model name while preserving recognizable brand tokens."""
        import re
        if not name:
            return "Speechify"
        clean = re.sub(r'[\\/*?:"<>|\s]', '_', str(name).strip())
        clean = re.sub(r'_+', '_', clean).strip('_ .')
        return clean or "Speechify"

    @staticmethod
    def get_versioned_filename(
        target_dir: str,
        base_name: str,
        model_name: str = "MP-SENet",
        disambiguator: Optional[str] = None,
        prefix: str = "enhanced_"
    ) -> str:
        """
        Computes the next logical version name strictly following:
        enhanced_{audio_file_name}_{model_name}_ver{xx}.wav

        Deterministic collision rule:
        Scans target_dir for matching files:
        enhanced_{audio_file_name}_{model_name}_ver(\\d+).wav
        If files exist (e.g. ver00, ver01, ver02, ver04), next version is max(versions) + 1 (e.g. ver05).
        If no matching files exist, next version is ver00.
        """
        import re
        os.makedirs(target_dir, exist_ok=True)
        safe_audio = AudioPipeline.sanitize_filename(base_name)
        safe_model = AudioPipeline.sanitize_model_name(model_name)

        # Strip any existing prefix or version suffixes from base_name to prevent nested naming
        if safe_audio.startswith(prefix):
            safe_audio = safe_audio[len(prefix):]
        # Strip trailing _ver\d+ or model tag if already present
        safe_audio = re.sub(r'_ver\d+$', '', safe_audio, flags=re.IGNORECASE)
        safe_audio = re.sub(rf'_{re.escape(safe_model)}$', '', safe_audio, flags=re.IGNORECASE)

        if disambiguator:
            safe_dis = AudioPipeline.sanitize_filename(disambiguator)
            if safe_dis not in safe_audio:
                safe_audio = f"{safe_audio}_{safe_dis}"

        # Match existing version files for this specific audio + model combination
        # Pattern: enhanced_{safe_audio}_{safe_model}_ver(\d+)\.wav
        pattern = re.compile(
            rf"^{re.escape(prefix)}{re.escape(safe_audio)}_{re.escape(safe_model)}_ver(\d+)\.wav$",
            re.IGNORECASE
        )

        existing_versions = []
        try:
            for fname in os.listdir(target_dir):
                match = pattern.match(fname)
                if match:
                    try:
                        v_num = int(match.group(1))
                        existing_versions.append(v_num)
                    except ValueError:
                        pass
        except Exception:
            pass

        if existing_versions:
            next_version = max(existing_versions) + 1
        else:
            next_version = 0

        filename = f"{prefix}{safe_audio}_{safe_model}_ver{next_version:02d}.wav"
        return os.path.join(target_dir, filename)

    @staticmethod
    def composite_timeline_audio(
        clips: list,
        in_sec: float,
        out_sec: float,
        sample_rate: int = 48000,
        output_path: Optional[str] = None
    ) -> Tuple[np.ndarray, Optional[str]]:
        """
        Extracts, resamples, and composites timeline clips across multiple audio tracks
        into a continuous sequence audio file, strictly preserving timeline gaps and timing.
        """
        total_duration = max(0.1, out_sec - in_sec)
        total_samples = int(round(total_duration * sample_rate))
        master_audio = np.zeros((total_samples,), dtype=np.float32)
        loaded_clips_count = 0
        candidate_clips_count = 0

        for clip in clips:
            media_path = clip.get("media_path") or clip.get("mediaPath")
            if not media_path or not os.path.isfile(media_path):
                continue

            clip_start = float(clip.get("start_time_sec") if clip.get("start_time_sec") is not None else clip.get("startTimeSec", 0.0))
            clip_dur = float(clip.get("duration_sec") if clip.get("duration_sec") is not None else clip.get("durationSec", 0.0))
            clip_in = float(clip.get("in_point_sec") if clip.get("in_point_sec") is not None else clip.get("inPointSec", 0.0))
            clip_out = float(clip.get("out_point_sec") if clip.get("out_point_sec") is not None else clip.get("outPointSec", clip_in + clip_dur))

            clip_end = clip_start + clip_dur
            if clip_end <= in_sec or clip_start >= out_sec:
                continue

            candidate_clips_count += 1

            try:
                data, extracted_sr, _, _ = AudioPipeline.load_audio_range(
                    media_path, in_sec=clip_in, out_sec=clip_out, target_sr=sample_rate
                )
                if data.ndim > 1:
                    data = np.mean(data, axis=1)

                dest_start = int(round(max(0.0, clip_start - in_sec) * sample_rate))
                if clip_start < in_sec:
                    src_offset = int(round((in_sec - clip_start) * sample_rate))
                    data = data[src_offset:]

                dest_end = min(total_samples, dest_start + len(data))
                samples_to_copy = max(0, dest_end - dest_start)

                if samples_to_copy > 0:
                    master_audio[dest_start:dest_start + samples_to_copy] += data[:samples_to_copy]
                    loaded_clips_count += 1
            except Exception:
                continue

        if candidate_clips_count > 0 and loaded_clips_count == 0:
            raise ValueError(f"Failed to extract audio from any of the {candidate_clips_count} clips in selected range.")

        rms = float(np.sqrt(np.mean(master_audio ** 2.0))) if len(master_audio) > 0 else 0.0
        peak = np.max(np.abs(master_audio)) if len(master_audio) > 0 else 0.0
        if peak > 1.0:
            master_audio = master_audio / (peak + 1e-6)

        if candidate_clips_count > 0 and rms < 1e-6:
            raise ValueError(f"Extracted audio track is silent (RMS: {rms:.7f}). Source media contains no audible signal.")

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            AudioPipeline.save_wav(output_path, master_audio, sample_rate, subtype="PCM_24")

        return master_audio, output_path

    @staticmethod
    def get_source_cache_key(
        sequence_guid: str,
        track_item_id: str,
        project_item_id: str,
        source_path: str,
        in_sec: float = 0.0,
        out_sec: float = 0.0,
        mtime: Optional[float] = None,
        file_size: Optional[int] = None
    ) -> str:
        """
        Builds a safe, compound cache key incorporating sequence identity,
        track item identity, project item identity, source path, range, and file modification stats.
        Prevents stale audio reuse across clip replacement, same-name files, or timeline moves.
        """
        import hashlib
        norm_path = os.path.normcase(os.path.abspath(source_path)) if source_path else ""
        if mtime is None and source_path and os.path.isfile(source_path):
            try:
                mtime = os.path.getmtime(source_path)
            except Exception:
                mtime = 0.0
        if file_size is None and source_path and os.path.isfile(source_path):
            try:
                file_size = os.path.getsize(source_path)
            except Exception:
                file_size = 0

        raw_key = (
            f"{sequence_guid}:{track_item_id}:{project_item_id}:{norm_path}:"
            f"{float(in_sec):.3f}:{float(out_sec):.3f}:{mtime}:{file_size}"
        )
        h = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return f"src_{h}"


validate_audio_signal = AudioPipeline.validate_audio_signal
