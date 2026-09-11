import os
import sys
import tempfile
import shutil
import numpy as np
import soundfile as sf
import scipy.signal
import torch

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.manager import ModelManager
from models.storage_manager import ModelStorageManager
from engine.models.zipenhancer_adapter import ZipEnhancerAdapter
from engine.models.mossformergan_adapter import MossFormerGANAdapter
from engine.models.mp_senet_adapter import MPSENetAdapter
from engine.models.deepfilternet_adapter import DeepFilterNetAdapter
from engine.validation.audio_validator import AudioValidator

def run_suite():
    print("=================================================================")
    print("       SPEECHIFY PRODUCTION ACCEPTANCE REGRESSION SUITE          ")
    print("=================================================================")
    results = {}

    # 1. Model Self-Tests
    print("\n--- TEST 1: Model Self-Tests (validateModelRuntime) ---")
    mgr = ModelManager()
    all_self_tests_passed = True
    for mid in ("mp_senet", "zipenhancer", "mossformergan", "deepfilternet3"):
        res = mgr.validate_model_runtime(mid)
        status = res.get("status")
        success = res.get("success", False)
        print(f"[{mid}]: status={status}, success={success}, device={res.get('device')}")
        if not success or status != "Ready":
            all_self_tests_passed = False
    results["model_self_tests"] = all_self_tests_passed
    assert all_self_tests_passed, "Model self-tests failed!"

    # 2. ZipEnhancer NaN & Silence Elimination (GPU & CPU)
    print("\n--- TEST 2: ZipEnhancer Numerical Integrity (GPU & CPU) ---")
    zip_ckpt = mgr.get_model_file_path("zipenhancer")
    assert zip_ckpt and os.path.isfile(zip_ckpt), f"ZipEnhancer checkpoint missing: {zip_ckpt}"

    # 2a. GPU (if available)
    if torch.cuda.is_available():
        adapter_gpu = ZipEnhancerAdapter("zipenhancer", {})
        adapter_gpu.initialize(zip_ckpt, "cuda:0")

        silence = np.zeros(32000, dtype=np.float32)
        out_silence = adapter_gpu.process(silence, 16000)
        assert not np.isnan(out_silence).any(), "ZipEnhancer GPU produced NaN on silence!"
        assert not np.isinf(out_silence).any(), "ZipEnhancer GPU produced Inf on silence!"
        assert np.max(np.abs(out_silence)) == 0.0, "ZipEnhancer GPU silence output is non-zero!"

        # Real / Synthetic speech audio test
        audio_path = r"c:\Users\grr22\Desktop\audio test\Sequence 01.mp3"
        if os.path.isfile(audio_path):
            audio, sr = sf.read(audio_path)
            if audio.ndim > 1: audio = audio[:, 0]
            audio_16k = scipy.signal.resample_poly(audio, 16000 // 441, 44100 // 441)[:48000]
        else:
            audio_16k = AudioGenerator.generate_speech_like(duration_sec=3.0, sr=16000)
        # Prepend and append silence
        audio_with_silence = np.concatenate([np.zeros(8000, dtype=np.float32), audio_16k, np.zeros(8000, dtype=np.float32)])

        out_audio = adapter_gpu.process(audio_with_silence, 16000)
        assert not np.isnan(out_audio).any(), "ZipEnhancer GPU produced NaN on real audio!"
        assert not np.isinf(out_audio).any(), "ZipEnhancer GPU produced Inf on real audio!"
        val = AudioValidator.validate(audio_with_silence, out_audio, 16000, 16000)
        assert val["valid"], f"AudioValidator failed on ZipEnhancer GPU output: {val['errors']}"
        print("[ZipEnhancer GPU]: PASS (0 NaN, 0 Inf, AudioValidator valid)")

    # 2b. CPU
    adapter_cpu = ZipEnhancerAdapter("zipenhancer", {})
    adapter_cpu.initialize(zip_ckpt, "cpu")
    out_cpu_silence = adapter_cpu.process(np.zeros(16000, dtype=np.float32), 16000)
    assert not np.isnan(out_cpu_silence).any(), "ZipEnhancer CPU produced NaN on silence!"
    assert not np.isinf(out_cpu_silence).any(), "ZipEnhancer CPU produced Inf on silence!"
    print("[ZipEnhancer CPU]: PASS (0 NaN, 0 Inf)")
    results["zipenhancer_integrity"] = True

    # 3. MossFormerGAN Real Inference (Zero manual setup)
    print("\n--- TEST 3: MossFormerGAN-SE Runtime & Inference ---")
    moss_ckpt = mgr.get_model_file_path("mossformergan")
    assert moss_ckpt and os.path.isfile(moss_ckpt), f"MossFormerGAN checkpoint missing: {moss_ckpt}"

    adapter_moss = MossFormerGANAdapter("mossformergan", {})
    adapter_moss.initialize(moss_ckpt, "cuda:0" if torch.cuda.is_available() else "cpu")
    out_moss = adapter_moss.process(audio_16k, 16000)
    assert not np.isnan(out_moss).any(), "MossFormerGAN produced NaN!"
    assert not np.isinf(out_moss).any(), "MossFormerGAN produced Inf!"
    rms_moss = float(np.sqrt(np.mean(out_moss ** 2)))
    assert rms_moss > 1e-4, f"MossFormerGAN output collapsed to zero energy (RMS={rms_moss})"
    val_moss = AudioValidator.validate(audio_16k, out_moss, 16000, 16000)
    assert val_moss["valid"], f"AudioValidator failed on MossFormerGAN output: {val_moss['errors']}"
    print(f"[MossFormerGAN]: PASS (RMS={rms_moss:.4f}, AudioValidator valid, no manual pip)")
    results["mossformergan_integrity"] = True

    # 4. MP-SENet Real Inference
    print("\n--- TEST 4: MP-SENet Runtime & Inference ---")
    mp_ckpt = mgr.get_model_file_path("mp_senet")
    assert mp_ckpt and os.path.isfile(mp_ckpt), f"MP-SENet checkpoint missing: {mp_ckpt}"
    adapter_mp = MPSENetAdapter("mp_senet", {})
    adapter_mp.initialize(mp_ckpt, "cuda:0" if torch.cuda.is_available() else "cpu")
    out_mp = adapter_mp.process(audio_16k, 16000)
    assert not np.isnan(out_mp).any(), "MP-SENet produced NaN!"
    assert not np.isinf(out_mp).any(), "MP-SENet produced Inf!"
    val_mp = AudioValidator.validate(audio_16k, out_mp, 16000, 16000)
    assert val_mp["valid"], f"AudioValidator failed on MP-SENet output: {val_mp['errors']}"
    print(f"[MP-SENet]: PASS (RMS={float(np.sqrt(np.mean(out_mp**2))):.4f}, AudioValidator valid)")
    results["mp_senet_integrity"] = True

    # 5. DeepFilterNet3 Real Inference (CPU & GPU)
    print("\n--- TEST 5: DeepFilterNet3 Runtime & Inference ---")
    df_ckpt = mgr.get_model_file_path("deepfilternet3")
    assert df_ckpt and os.path.isfile(df_ckpt), f"DeepFilterNet checkpoint missing: {df_ckpt}"
    dummy_48k = np.random.randn(48000).astype(np.float32) * 0.1

    # CPU
    adapter_df_cpu = DeepFilterNetAdapter("deepfilternet3", {})
    adapter_df_cpu.initialize(df_ckpt, "cpu")
    out_df_cpu = adapter_df_cpu.process(dummy_48k, 48000)
    assert not np.isnan(out_df_cpu).any(), "DeepFilterNet CPU produced NaN!"
    print("[DeepFilterNet3 CPU]: PASS")

    # GPU
    if torch.cuda.is_available():
        adapter_df_gpu = DeepFilterNetAdapter("deepfilternet3", {})
        adapter_df_gpu.initialize(df_ckpt, "cuda:0")
        out_df_gpu = adapter_df_gpu.process(dummy_48k, 48000)
        assert not np.isnan(out_df_gpu).any(), "DeepFilterNet GPU produced NaN!"
        print("[DeepFilterNet3 GPU]: PASS")
    results["deepfilternet_integrity"] = True

    # 6. Model Storage Switching & Zero Silent Copying
    print("\n--- TEST 6: Model Storage Switching & Zero Silent Copying ---")
    sm = ModelStorageManager()
    orig_path = sm.get_storage_path()
    temp_empty = tempfile.mkdtemp(prefix="speechify_test_empty_")
    try:
        res = sm.set_storage_path(temp_empty)
        assert res["models_count"] == 0, f"Expected 0 models in empty folder, got {res['models_count']}"
        assert len(os.listdir(temp_empty)) == 0, "Empty directory was silently modified or copied into!"
        print("[Empty Storage Switching]: PASS (0 models, 0 copied files)")
    finally:
        sm.set_storage_path(orig_path)
        shutil.rmtree(temp_empty, ignore_errors=True)

    # Verify restoration
    res_restored = sm.scan_current_storage()
    installed_restored = len([m for m in res_restored.values() if m.get("installed")])
    assert installed_restored >= 4, f"Expected at least 4 models in restored storage, got {installed_restored}"
    print(f"[Restored Storage Discovery]: PASS ({installed_restored} models discovered)")
    results["storage_switching"] = True

    print("\n=================================================================")
    print("       ALL ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!              ")
    print("=================================================================")
    for k, v in results.items():
        print(f"  - {k}: {'PASS' if v else 'FAIL'}")

if __name__ == "__main__":
    run_suite()
