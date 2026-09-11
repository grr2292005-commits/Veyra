#!/usr/bin/env python3
"""
Test smoke test for the four required production models:
- mp_senet
- zipenhancer
- deepfilternet3
- mossformergan
"""

import os
import sys
import numpy as np
import soundfile as sf
import tempfile
import torch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.models.factory import ModelFactory
from models.storage_manager import ModelStorageManager, FOLDER_ALIASES

def test_all_models():
    print("=== Testing Four Production Model Adapters ===")
    models_dir = os.path.join(BASE_DIR, "models")
    storage_mgr = ModelStorageManager(models_dir)
    
    # Checkpoint directory: release-portable has all 4 models
    portable_storage = os.path.join(BASE_DIR, "release-portable", "models", "storage")
    
    models_to_test = [
        ("deepfilternet3", "deepfilternet3/model_120.ckpt.best"),
        ("mp_senet", "mp_senet/g_best_dns"),
        ("zipenhancer", "zipenhancer/pytorch_model.bin"),
        ("mossformergan", "mossformergan/last_best_checkpoint.pt")
    ]
    
    # Generate 1.0s synthetic 48kHz audio test signal
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    test_signal = 0.3 * np.sin(2 * np.pi * 440 * t) # 440 Hz tone
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_wav = os.path.join(tmp_dir, "test_input.wav")
        output_wav = os.path.join(tmp_dir, "test_output.wav")
        sf.write(input_wav, test_signal, sr)
        
        for mid, rel_ckpt in models_to_test:
            print(f"\n--- Testing Model: {mid} ---")
            ckpt_path = os.path.join(portable_storage, rel_ckpt)
            if not os.path.isfile(ckpt_path):
                print(f"[FAIL] Checkpoint not found at {ckpt_path}")
                return False
                
            print(f"Creating adapter for {mid} with {ckpt_path}...")
            adapter = ModelFactory.create_adapter(mid, ckpt_path, device="cpu")
            if not adapter.is_initialized():
                print(f"[FAIL] Failed to initialize {mid}")
                return False
            print(f"[PASS] Adapter {mid} initialized successfully.")
            
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
            print(f"Running self_test on {mid} (device: {dev})...")
            res = adapter.self_test(ckpt_path, device=dev)
            print(f"Self-test result for {mid}: {res}")
            if not res.get("success"):
                print(f"[FAIL] Self-test failed for {mid}: {res.get('error')}")
                return False
            print(f"[PASS] Model {mid} passed complete inference smoke test.")
            
    print("\n=== ALL FOUR PRODUCTION MODELS PASSED INFERENCE SMOKE TEST ===")
    return True

if __name__ == "__main__":
    success = test_all_models()
    sys.exit(0 if success else 1)
