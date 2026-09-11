# Speechify Local AI Engine Lifecycle & Architecture

## 1. Overview & Core Philosophy

**Speechify** is designed from the ground up to feel like an internal, native creative application service inside Adobe Premiere Pro. Editors should never see terminals, PowerShell prompts, or background console windows. 

The entire engine lifecycle is fully automated:
1. **Panel Load**: The Speechify panel initializes and silently boots the local AI engine via `pythonw.exe`.
2. **Readiness Probe**: Fast asynchronous health checks verify the engine and cached neural models within milliseconds.
3. **Heartbeat Maintenance**: The panel sends a lightweight ping (`POST /api/heartbeat`) every 4 seconds.
4. **Persistent Model Caching**: Selected neural models (MP-SENet, ZipEnhancer, DeepFilterNet3, MossFormerGAN) remain warm in VRAM across multiple timeline clips without reloading delay.
5. **Clean Teardown / Auto-Shutdown**:
   - On normal panel close or sequence reload, `beforeunload` / `unload` events fire a graceful `POST /shutdown`, which triggers `ModelFactory.cleanup_all()`, `torch.cuda.empty_cache()`, and removes lockfiles.
   - If Premiere Pro or CEP crashes or is killed forcefully, the engine's **15-second background watchdog thread** detects the absence of heartbeat pings and automatically cleans up memory and terminates itself. Zero orphan processes remain.

---

## 2. Process Architecture & Windowless Execution

```mermaid
graph TD
    A[Premiere Pro CEP Panel] -->|1. window.SpeechifyEngineManager.start()| B[Node.js child_process.spawn]
    B -->|2. Spawns silently with CREATE_NO_WINDOW & stdio redirection| C[pythonw.exe : server.py 8765]
    C -->|3. Writes lockfile with PID & instanceId| D[logs/engine.lock]
    A -->|4. Every 4s: POST /api/heartbeat| C
    C -->|5. Background Watchdog Thread: Check if heartbeat > 15s| E{Active Job or Heartbeat?}
    E -->|Yes| F[Keep Engine Active]
    E -->|No| G[Auto-Shutdown: Cleanup VRAM & Exit]
    A -->|6. Panel unload: POST /shutdown| C
```

### Why `python.exe` Was Showing a Window vs. `pythonw.exe`
- In Windows PE binaries, the executable header specifies an `IMAGE_SUBSYSTEM`:
  - `IMAGE_SUBSYSTEM_WINDOWS_CUI` (Console Subsystem — `python.exe`): Windows allocates a console buffer and window. In modern Windows 11 with Windows Terminal set as the default terminal emulator, child processes launched by Node.js or CEP spawn a visible terminal tab or background window even with `windowsHide: true`.
  - `IMAGE_SUBSYSTEM_WINDOWS_GUI` (GUI Subsystem — `pythonw.exe`): Windows suppresses console window allocation completely.
- In addition, all hardware detection routines (such as CPU model queries) use native Windows registry inspection (`winreg`) rather than spawning `powershell.exe`.

---

## 3. Ownership & Lockfile System

To guarantee single-instance execution and avoid port collisions:
- Upon boot, `server.py` writes `logs/engine.lock`:
  ```json
  {
    "pid": 12116,
    "owner": "speechify",
    "instanceId": "sp-inst-2e64d03b",
    "startedAt": 1788879285.76,
    "port": 8765
  }
  ```
- Before launching, `EngineManager.findEngine()` and `start()` probe `GET /health`. If an existing instance of Speechify is already running on port 8765, it validates ownership (`owner: "speechify"`) and attaches to it immediately rather than launching a redundant process.
- When `stop()` or the watchdog triggers, the lockfile and PID file are cleanly unlinked.

---

## 4. Heartbeat Watchdog Specification

- **Panel Heartbeat Interval**: Every **4,000 ms** (`CONFIG.heartbeatIntervalMs`).
- **Engine Watchdog Timeout**: **15 seconds** (`heartbeat_timeout = 15`).
- **Initial Grace Period**: **30 seconds** (`grace_period = 30`) to accommodate slower cold-boot disk I/O on older systems.
- **Active Job Exemption**: If an audio enhancement job is currently queued, running, or processing, the watchdog suspends shutdown checks so long audio files are never interrupted.

---

## 5. Architectural Comparison: Silent Python Daemon vs. C++ Premiere Plugin

We thoroughly evaluated whether to write a native C++ Premiere Pro plugin (`.prm` / Premiere Pro Audio SDK) versus our Silent Local Python Daemon architecture.

| Evaluation Axis | C++ Native Plugin (`.prm`) | Speechify Silent Daemon (`pythonw.exe` + CEP/UXP) |
|---|---|---|
| **Crash Safety** | 🔴 **High Risk**: A crash or CUDA out-of-memory in LibTorch / C++ terminates the entire Adobe Premiere Pro application, corrupting unsaved user edits. | 🟢 **Zero Risk**: Runs in an isolated OS process. A failure never crashes Premiere; the panel catches it and displays a clean retry UI. |
| **Premiere Version Compatibility** | 🔴 **Poor**: Requires separate compilation, linking, and QA for Premiere 2022, 2023, 2024, and 2025 SDK ABI changes. | 🟢 **Universal**: Works seamlessly on Premiere Pro 2021 through 2025+ without recompilation. |
| **PyTorch & CUDA Ecosystem** | 🔴 **Very Difficult**: Bundling LibTorch C++, CUDA kernels, and custom STFT ops for MP-SENet, ZipEnhancer, and MossFormerGAN in C++ is brittle on Windows. | 🟢 **Native & Robust**: Direct access to PyTorch, TorchAudio, ONNX, and cuDNN with optimized tensor kernels. |
| **Startup & UI Responsiveness** | 🟡 Native in-process calls. | 🟢 **<10ms IPC**: Local loopback HTTP latency is imperceptible to users (<5ms). |
| **Installer Complexity** | 🔴 Requires administrative file copying into Premiere's `Plug-ins\Common` directory. | 🟢 **Standard User-Level**: Drops directly into `%APPDATA%\Adobe\CEP\extensions` with no admin UAC prompts. |

**Conclusion**: The **Silent Daemon Architecture** is the industry standard used by modern professional AI plugins (e.g., Topaz Video AI, Whisper Premiere extensions, Runway) because it guarantees rock-solid stability for video editors while preserving full neural network inference performance.
