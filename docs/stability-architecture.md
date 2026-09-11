# Speechify — Stability Architecture & Lifecycle Specification

## Overview

This specification details the hardened, deterministic architecture implemented during the **Speechify Final Stabilization Pass**. It guarantees zero console/terminal popups, single-source-of-truth state management, non-destructive model folder configuration, custom theme-compliant controls, and transparent technical diagnostics.

---

## 1. Unified AppState Store (`plugin/state/app_state.js`)

`SpeechifyAppState` acts as the single source of truth across all extension components:
- **Engine State**: Tracks online status, startup progress, PID, port, instance ID, and error messages.
- **Hardware State**: Holds raw system profile, CPU model, GPU name, VRAM, and detected execution backends.
- **Model Storage**: Holds current directory path and validated installed model count.
- **Models Registry**: Key-value dictionary of all supported neural models and their installation/checkpoint status.
- **Processing Device**: Tracks selected device ID, recommended device, and list of validated available devices.
- **Premiere State**: Tracks active sequence metadata (name, duration, in/out, sample rate) and selected audio clips.
- **Settings**: Audio normalization, placement mode, and UI preferences.

### Subscription Pattern
Any UI or service component can subscribe to state changes via:
```javascript
const unsubscribe = window.SpeechifyAppState.subscribe((state) => {
  // Reactive UI update
});
```

---

## 2. Authoritative Path Resolution (`plugin/services/path_manager.js`)

Path resolution is completely deterministic and decoupled from hardcoded paths:
1. Checks for bundled configuration file (`engine_config.json`).
2. Checks local workspace paths relative to project root (`benchmark_archive/benchmark_envs/zipenhancer/Scripts/pythonw.exe`).
3. Checks Windows registry / environment variables.
4. Windows execution strictly prioritizes `pythonw.exe` over `python.exe` to guarantee zero console window allocation.
5. All resolved paths are validated for existence with `fs.existsSync` before use.

---

## 3. Silent Engine Lifecycle (`plugin/premiere/engine_manager.js`)

### Silent Spawning Guarantees
- Process binary: `pythonw.exe` (Windows Subsystem: Windows GUI, NOT Console).
- Options:
  - `detached: true`
  - `windowsHide: true`
  - `stdio: ['ignore', stdoutStream, stderrStream]`
- Prevents Windows command prompt, PowerShell, or Python console from appearing at any point during engine startup, inference, or shutdown.

### Startup Diagnostics
All lifecycle steps and timestamps are appended to `logs/engine-startup.log`:
```text
[21:27:35] EngineManager: runtime found: ...\pythonw.exe
[21:27:35] EngineManager: spawning engine: "...\pythonw.exe" "...\server.py" 8765
[21:27:35] EngineManager: process PID 6032
[21:27:35] EngineManager: waiting for health check (timeout: 15s)
[21:27:38] EngineManager: health check passed in 3053ms (PID: 26676)
[21:27:38] EngineManager: READY
```

### Single-Instance & Lockfile Protection
- Port 8765 health is probed prior to spawning.
- If an existing healthy instance is running, it is reused immediately.
- On startup, the engine writes an ownership file (`engine.lock`) containing PID, instance ID, and start timestamp.
- On clean exit, the lockfile is removed.
- Watchdog heartbeat prevents orphaned processes: if Premiere Pro closes without unhooking, the engine self-terminates after 15 seconds without a heartbeat.

---

## 4. Storage Architecture (`plugin/services/storage_service.js`)

### Zero Implicit Copying
- Setting a new model storage directory updates `ModelManager`'s active scan directory only.
- Switching to an empty folder reports 0 installed models and provides direct download actions in "Manage Models".
- Models are **never copied or duplicated automatically**.

### Explicit Migration Workflow
- If users want to migrate existing downloaded weights from one folder to another, they use the dedicated "Move existing models..." dialog.
- `StorageService.migrateModels()` safely moves weights, verifies checksums in the target directory, cleans up the source, and refreshes the model registry.

### Folder Selection
- Interactive folder browsing uses `window.cep.fs.showOpenDialogEx` (in CEP mode) or UXP `localFileSystem.getFolder()` with clean fallback to manual entry.

---

## 5. Custom UI Controls & Status Indicators

### Custom Processing Device Dropdown (`#deviceDropdown`)
- Replaced native browser `<select>` with a custom dark-themed dropdown adhering to the Speechify design tokens (`tokens.css`).
- Fully accessible with `role="combobox"` and `role="listbox"`.
- Supports keyboard navigation (Escape to dismiss, outside click to dismiss).
- Options dynamically reflect detected hardware (GPU model, VRAM capacity, CPU, and Recommended Automatic mode).
- User preference persists in `localStorage`.

### Minimal Ready Indicator (`#readyStatusDot`)
- Located in the top header adjacent to the "Speechify Local AI" title.
- Small green dot `●` appears exclusively when the engine status is `ready`.
- No intrusive giant status cards or banner pills during normal usage.
- Temporary "Starting speech engine…" text appears only during initial engine boot and fades out once ready.

---

## 6. User-Facing Error Translation Matrix

No raw developer exceptions (such as `Failed to fetch`, `TypeError: undefined is not an object`, or Windows file system errors) are ever displayed in the UI:

| Technical Error Pattern | User-Facing Message |
| :--- | :--- |
| `Failed to fetch`, `ECONNREFUSED` | *"The speech engine is unreachable. Please verify it is running or click Retry."* |
| `ENOENT`, `FileNotFoundError` | *"The specified audio file or model could not be found."* |
| `EACCES`, `PermissionError` | *"Access was denied by your system. Please check folder permissions."* |
| `Missing 'source_file'` | *"Speechify couldn't locate source audio for the selected clips."* |
| Python Stacktrace | Extracted clean message body without technical runtime prefixes. |
