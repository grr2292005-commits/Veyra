# Speechify — Processing Hardware & Device Selection

## 1. Overview

Speechify supports flexible hardware acceleration across modern NVIDIA GPUs and multi-core x86_64 CPUs. Users can configure device execution via **Settings → Performance → Processing Device**.

---

## 2. Device Modes

| Option | PyTorch Device | Description |
| :--- | :--- | :--- |
| **Automatic (Recommended)** | `cuda` (if available) / `cpu` | Automatically detects the primary CUDA GPU with sufficient VRAM. Falls back to CPU if no compatible GPU is present. |
| **GPU — NVIDIA RTX 4050** | `cuda:0` | Enforces CUDA execution on the dedicated NVIDIA graphics card for maximum throughput (~$7\times$ to $8\times$ realtime). |
| **CPU — System Processor** | `cpu` | Enforces PyTorch execution on the system CPU using vectorized AVX2/AVX-512 routines. Useful when exporting heavy video rendering on GPU. |

---

## 3. Runtime Resolution & Dynamic Switching

When a job arrives at `/api/enhance`:

```python
target_device = request_device  # 'auto', 'cuda', 'cpu'

if target_device == "auto":
    device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
elif target_device.startswith("cuda"):
    device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
else:
    device_str = "cpu"
```

### Hot Adapter Reloading
In `engine/models/factory.py`, the `ModelFactory` tracks the active adapter's device:

```python
if model_id in self._adapters:
    adapter = self._adapters[model_id]
    if adapter.device.type != target_device.type:
        # User switched devices between jobs
        adapter.to(target_device)
    return adapter
```

If the user changes the device selector from GPU to CPU (or vice versa), the adapter seamlessly migrates without restarting the engine.
