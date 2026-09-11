# Speechify — Hardware Detection & Acceleration Architecture

## 1. Authoritative Hardware Manager

Hardware detection and capability profiling is owned by **`HardwareManager`** (`engine/hardware/detector.py`). It profiles host CPU, total system RAM, dedicated NVIDIA GPUs, VRAM capacity, and PyTorch CUDA backend support.

---

## 2. Detection Protocol

### CPU & RAM Profiling
- Uses native Windows Registry query (`HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`) and Python `platform` / `psutil`.
- Avoids external `powershell.exe` subprocesses, eliminating console flashing during hardware probes.

### GPU & CUDA Detection
1. **PyTorch CUDA Backend**: Tests `torch.cuda.is_available()`, `torch.cuda.device_count()`, and device properties (`torch.cuda.get_device_properties(0)`).
2. **Dedicated VRAM**: Queries `total_memory` (in GB). For example, on the NVIDIA RTX 4050 Laptop GPU:
   - GPU Name: `NVIDIA GeForce RTX 4050 Laptop GPU`
   - Dedicated VRAM: `6.0 GB`
   - Device String: `cuda:0`
3. **Dynamic Device Dropdown Options**:
   When CUDA is available, `get_available_devices()` exposes:
   - `Automatic (Recommended)` (`auto`)
   - `GPU — NVIDIA GeForce RTX 4050 Laptop GPU (6.0 GB)` (`cuda:0`)
   - `CPU — System Processor` (`cpu`)

---

## 3. Strict Execution Routing (Zero Silent Fallback)

In production creative workflows, silently falling back to CPU when the user explicitly selected GPU causes unexpected slowdowns and hides configuration issues.

Speechify enforces **strict hardware routing**:
- **Explicit `cuda` Request**: If the user selects `GPU` or sends `device: "cuda"`:
  ```python
  if device.startswith("cuda") and not torch.cuda.is_available():
      raise RuntimeError(
          "Requested GPU acceleration ('cuda'), but CUDA is not available or no compatible GPU was detected. "
          "Please verify NVIDIA drivers or select CPU in Settings."
      )
  ```
  The engine fails fast with an informative error rather than silently processing at $10\times$ slower speeds on CPU.
- **`Automatic` Mode**: If the user selects `Automatic`:
  - Resolves to `cuda:0` if CUDA is available and functional.
  - Resolves to `cpu` if no CUDA GPU is present.

---

## 4. VRAM Safety & Pre-Flight Check

Before launching heavy neural model inference, `SpeechifyOrchestrator` performs a VRAM pre-flight check:
1. Compares model VRAM requirements against available free VRAM.
2. If free VRAM is tight (< 400 MB), triggers `torch.cuda.empty_cache()` and garbage collection before weight loading.
3. Audio chunking (Hann overlap-add with 2.0s windows) keeps peak VRAM for MP-SENet below 600 MB, easily fitting within 6GB and 4GB cards.
