import os
import sys
import json
import time
from typing import Dict, Any

# Ensure project root in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def runProductionHealthCheck(save_path: str = None) -> Dict[str, Any]:
    """
    Evaluates runtime, filesystem, hardware, engine, models, and audio pipeline.
    Returns structured diagnostic status.
    """
    report = {
        "timestamp": time.time(),
        "runtime": "FAIL",
        "filesystem": "FAIL",
        "hardware": "FAIL",
        "engine": "FAIL",
        "audio_pipeline": "FAIL",
        "models": {
            "mp_senet": "FAIL",
            "zipenhancer": "FAIL",
            "mossformergan": "FAIL",
            "deepfilternet3": "FAIL"
        },
        "details": {}
    }

    # 1. Runtime check
    try:
        import torch
        import soundfile
        import scipy
        report["runtime"] = "PASS"
        report["details"]["torch_version"] = torch.__version__
        report["details"]["cuda_available"] = torch.cuda.is_available()
    except Exception as e:
        report["details"]["runtime_error"] = str(e)

    # 2. Filesystem check
    try:
        from models.storage_manager import ModelStorageManager
        sm = ModelStorageManager()
        spath = sm.get_storage_path()
        readable = os.access(spath, os.R_OK) if os.path.exists(spath) else False
        writable = os.access(spath, os.W_OK) if os.path.exists(spath) else False
        if os.path.isdir(spath) and readable:
            report["filesystem"] = "PASS"
        report["details"]["storage_path"] = spath
        report["details"]["storage_readable"] = readable
        report["details"]["storage_writable"] = writable
    except Exception as e:
        report["details"]["filesystem_error"] = str(e)

    # 3. Hardware check
    try:
        from engine.hardware.detector import HardwareDetector
        det = HardwareDetector()
        prof = det.get_profile(refresh=False)
        if prof and ("available_devices" in prof or "gpus" in prof or "cpu" in prof):
            report["hardware"] = "PASS"
            report["details"]["gpu_count"] = len(prof.get("gpus", []))
            report["details"]["recommended_device"] = prof.get("recommendedDevice")
    except Exception as e:
        report["details"]["hardware_error"] = str(e)

    # 4. Engine & Audio Pipeline check
    try:
        from engine.audio.pipeline import AudioPipeline
        from engine.validation.audio_validator import AudioValidator
        import numpy as np
        
        # Test pipeline on micro tone
        t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
        tone = np.sin(2 * np.pi * 440 * t)
        resampled = AudioPipeline.resample(tone, 16000, 48000)
        val = AudioValidator.validate(resampled, resampled, 48000, 48000)
        if val["valid"]:
            report["audio_pipeline"] = "PASS"
            report["engine"] = "PASS"
    except Exception as e:
        report["details"]["audio_pipeline_error"] = str(e)

    # 5. Models check
    try:
        from models.manager import ModelManager
        mm = ModelManager()
        for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
            try:
                ckpt = mm.get_model_file_path(mid)
                if ckpt and os.path.isfile(ckpt) and os.path.getsize(ckpt) > 100000:
                    report["models"][mid] = "PASS"
                else:
                    report["models"][mid] = "FAIL"
            except Exception:
                report["models"][mid] = "FAIL"
    except Exception as e:
        report["details"]["models_error"] = str(e)

    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report

if __name__ == "__main__":
    out_path = os.path.join(BASE_DIR, "tests", "health_report.json")
    res = runProductionHealthCheck(out_path)
    print(json.dumps(res, indent=2))
