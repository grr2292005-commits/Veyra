# Speechify — Local AI Engine Lifecycle & Architecture

## 1. Overview & Core Philosophy

**Speechify** is engineered to behave like a native creative application service inside Adobe Premiere Pro. Video editors should never see terminals, PowerShell windows, or command prompts during normal usage.

The entire engine lifecycle is fully automated:
1. **Panel Load**: Speechify initializes and silently launches its local AI engine via `pythonw.exe`.
2. **Readiness Probe**: Asynchronous health checks verify the engine within a strict 15-second startup timeout.
3. **Heartbeat Maintenance**: The panel sends a lightweight ping (`POST /api/heartbeat`) every 4 seconds.
4. **Persistent Model Caching**: Selected neural models (MP-SENet, ZipEnhancer, DeepFilterNet3, MossFormerGAN) remain warm in memory across multiple timeline clips without reloading delay.
5. **Clean Teardown / Auto-Shutdown**:
   - On normal panel close or sequence reload, `beforeunload` fires a graceful `POST /shutdown`, which triggers `ModelFactory.cleanup_all()`, releases GPU memory, and unlinks lockfiles.
   - If Premiere Pro or CEP crashes or terminates forcefully, the engine's **15-second background watchdog thread** detects the absence of heartbeat pings and automatically cleans up memory and terminates itself. Zero orphan processes remain.

---

## 2. Process Architecture & Windowless Execution

```mermaid
graph TD
    A[Premiere Pro Extension Panel] -->|1. window.SpeechifyEngineManager.start()| B[Node.js child_process.spawn]
    B -->|2. Spawns silently with CREATE_NO_WINDOW & stdio redirection| C[pythonw.exe : server.py 8765]
    C -->|3. Writes lockfile with PID & instanceId| D[logs/engine.lock]
    A -->|4. Every 4s: POST /api/heartbeat| C
    C -->|5. Background Watchdog: Checks heartbeat freshness| E{Active Job or Recent Heartbeat?}
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
    "pid": 34032,
    "owner": "speechify",
    "instanceId": "sp-inst-41d5dc0e",
    "startedAt": 1788969730.06,
    "port": 8765
  }
  ```
- Before launching, `EngineManager.findEngine()` and `start()` probe `GET /health`. If an existing instance of Speechify is already running on port 8765, it validates ownership (`owner: "speechify"`) and attaches to it immediately rather than launching a redundant process.
- **Process Teardown Safety**: When `stop()` is invoked, it only terminates the specific child process PID recorded in `engine.lock`. It **NEVER executes global process kills** like `taskkill /IM python.exe /F`, ensuring other Python processes on the user's workstation are completely untouched.
- When `stop()` or the watchdog triggers, the lockfile and PID file are cleanly unlinked.

---

## 4. Heartbeat Watchdog Specification

- **Panel Heartbeat Interval**: Every **4,000 ms** (`CONFIG.heartbeatIntervalMs`).
- **Engine Watchdog Timeout**: **15 seconds** (`heartbeat_timeout = 15`).
- **Initial Grace Period**: **30 seconds** (`grace_period = 30`) to accommodate cold-boot disk I/O on older systems.
- **Active Job Exemption**: If an audio enhancement job is currently queued, running, or processing, the watchdog suspends shutdown checks so long audio files are never interrupted.

---

## 5. Startup Sequence & Timeout Protection

1. `init()` checks for an already-running engine on `127.0.0.1:8765`.
2. If healthy, updates UI immediately to `ready`.
3. If not running, launches `pythonw.exe` with `detached: true`, `windowsHide: true`, and standard file descriptor redirection.
4. Fast exponential-backoff polling checks `/health` every 250ms–500ms.
5. If the engine does not report healthy within **15 seconds**, the startup promise rejects, setting state to `error` and presenting a minimal **Retry** button with error diagnosis. The UI **never freezes indefinitely in `Starting…`**.
