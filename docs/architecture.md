# Architecture Specification — Speechify for Adobe Premiere Pro

**Speechify** is a 100% offline, local AI speech enhancement extension engineered for **Adobe Premiere Pro 2024 / 2025+** on Windows 11 with NVIDIA RTX acceleration.

---

## 1. High-Level Architecture Overview

Speechify operates via two decoupled execution domains communicating over a low-latency local loopback interface (`http://127.0.0.1:8765`):

```mermaid
graph TD
    subgraph Adobe Premiere Pro Environment
        A[Active Sequence] -->|Timeline Selection & In/Out| B[Speechify Extension Panel]
        B -->|ExtendScript / DOM Bridge| C[Native Premiere Pro DOM]
        C -->|Audio Media File & Timings| B
        D[Speechify Project Bin] -->|Non-destructive Placement| A
    end

    subgraph IPC Loopback (127.0.0.1:8765)
        B <-->|REST JSON & Heartbeat| E[Speechify Python Engine Daemon]
    end

    subgraph Speechify Engine Daemon (pythonw.exe)
        E --> F[HardwareManager]
        E --> G[ModelStorageManager]
        E --> H[SpeechifyOrchestrator]
        H --> I[Audio Pipeline: Resampling & Normalization]
        H --> J[Neural Model Adapters]
        J --> K[MP-SENet / ZipEnhancer / DeepFilterNet3 / MossFormerGAN]
        H --> L[Enhanced 24-Bit 48kHz WAV Output]
    end

    L -.->|Direct Import via Bridge| D
```

---

## 2. The Three Authoritative Systems

To eliminate race conditions and inconsistent states, Speechify divides operational responsibilities into three single sources of truth:

### A. EngineLifecycleManager (`plugin/premiere/engine_manager.js`)
- **Authority over**: Engine process state (`stopped`, `starting`, `ready`, `error`, `restarting`), silent startup via `pythonw.exe`, PID tracking in `logs/engine.lock`, 15-second startup timeout, 4-second heartbeat pings, and clean graceful teardown.
- **Key Guarantee**: Spawns windowless processes without console flashing; never uses global `taskkill /IM python.exe` (only kills owned child PID); watchdog shuts down engine within 15 seconds if host dies.

### B. ModelStorageManager (`models/storage_manager.py` & `plugin/services/storage_service.js`)
- **Authority over**: Active model storage directory resolution, default managed location (`%APPDATA%\Speechify\Models`), automatic subfolder scaffolding, physical checkpoint presence and minimum size validation, non-destructive path switching, and explicit user-confirmed migrations.
- **Key Guarantee**: Zero required setup on first run; switching location never copies files automatically; clean UI labels without confusing technical paths.

### C. HardwareManager (`engine/hardware/detector.py`)
- **Authority over**: Host CPU profiling via Windows registry, total system RAM, dedicated NVIDIA GPU discovery, CUDA capability verification, dynamic device dropdown options, VRAM pre-flight checks, and strict execution routing.
- **Key Guarantee**: Strict routing when GPU is selected (no silent CPU fallback; throws informative error if CUDA is unavailable); provides VRAM safety margins for low-memory cards.

---

## 3. Centralized Application State (`plugin/state/app_state.js`)

All frontend UI views, dropdowns, and status badges derive their state from a single reactive store: **`SpeechifyAppState`**.

```javascript
AppState = {
  engine: { status, pid, port, version, error, lastHealth },
  hardware: { cpu, ramGB, gpu, gpus, backends, tier, tierName },
  modelStorage: { path, rawPath, isManaged, displayTitle, displaySubtext, accessible, error, modelsCount },
  models: { ... },
  processingDevice: { mode, resolvedDevice, availableDevices: [...] },
  premiere: { activeSequence, selectedClips, scope },
  settings: { normalize, placementMode }
}
```

Components subscribe to specific slices (`engine`, `hardware`, `modelStorage`, `models`, `processingDevice`) ensuring UI elements react instantly to background changes.

---

## 4. Timeline Processing & Audio Pipeline

1. **Extraction**: `dom_bridge.js` extracts audio clip boundaries from the Premiere Pro timeline.
2. **Audio Processing**:
   - Resamples inputs accurately to the model's native rate (16 kHz for MP-SENet/ZipEnhancer/MossFormerGAN, 48 kHz for DeepFilterNet3).
   - Runs chunked neural inference using Hann overlap-add windows.
   - Restores native sample rate (48 kHz, 24-bit PCM WAV).
   - Optional EBU R128 loudness normalization (-24 LUFS).
3. **Placement**: Imports the resulting audio directly into a dedicated `"Speechify"` project bin and inserts it into the sequence on a new audio track with exact timeline alignment and gap preservation.
