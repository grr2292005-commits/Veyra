# Troubleshooting & Diagnostics — Speechify for Adobe Premiere Pro

This guide outlines common operational questions, error states, and diagnostic procedures for Speechify.

---

## 1. Startup Issues & Timeout Diagnostics

### Symptom: Header shows "Starting…" for 15 seconds then displays an error
Speechify enforces a strict 15-second timeout during engine boot. If the local speech engine does not become healthy within 15 seconds, it transitions to an error state and provides a **Retry** button instead of hanging indefinitely.

**Diagnosing the Cause**:
1. Inspect the engine log file:
   ```text
   SpeechEnhancerPro/logs/engine.log
   ```
2. Check if a zombie or orphaned process is holding port 8765:
   ```powershell
   Get-NetTCPConnection -LocalPort 8765
   ```
3. If an old process is lingering, remove the stale lockfile:
   ```powershell
   Remove-Item "SpeechEnhancerPro\logs\engine.lock" -Force
   ```
4. Click the **Retry** icon in the Speechify header.

---

## 2. GPU Detection & Hardware Diagnostics

### Symptom: "Performance" section displays CPU only, or GPU is missing
If you have an NVIDIA GPU (e.g. RTX 4050) but Speechify only shows CPU:

**Checks**:
1. **NVIDIA Graphics Driver**:
   Ensure you have recent NVIDIA Game Ready or Studio Drivers installed (version 530+ recommended).
2. **CUDA Compatibility**:
   In PowerShell, test your environment's PyTorch CUDA support:
   ```powershell
   & "benchmark_archive\benchmark_envs\zipenhancer\Scripts\python.exe" -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
   ```
3. **Strict Device Routing**:
   If you select `GPU` in Settings and the GPU becomes unavailable, Speechify will raise an explicit error rather than silently processing on CPU at $10\times$ slower speeds.

---

## 3. Model Storage & Missing Models

### Symptom: Models are marked as "Available to download" instead of "Installed"
1. **Default Managed Storage**:
   Speechify's managed default storage is located at:
   ```text
   %APPDATA%\Speechify\Models
   ```
   Check that subfolders exist (`MP-SENet`, `ZipEnhancer-S`, `MossFormerGAN-SE`, `DeepFilterNet3`).
2. **First Run Model Seeding**:
   If checkpoints exist in `SpeechEnhancerPro/models/storage` or `benchmark_archive/checkpoints/`, `ModelStorageManager` automatically discovers them.
3. **Switching Folders**:
   If you switched storage locations to a new folder, changing the location does not copy files automatically. Use the **`[ Move existing models… ]`** button in Settings to transfer your model weights cleanly.

---

## 4. Port Conflict on Port 8765

Speechify binds to `http://127.0.0.1:8765` by default.

To verify what process is using port 8765:
```powershell
Get-NetTCPConnection -LocalPort 8765 | Select-Object OwningProcess, State
```

If another application occupies this port, you can customize the port by launching `engine/server.py <port>` or configuring the engine manager port in `plugin/premiere/engine_manager.js`.

---

## 5. Timeline Synchronization & Selection

### Symptom: "No sequence open" or "No clips selected"
- **Active Sequence**: Ensure a timeline sequence tab is actively open and focused in Premiere Pro.
- **Clip Selection**: Highlight one or more dialogue audio clips in your sequence timeline.
- **Entire Sequence Mode**: If you want to enhance the whole timeline at once, switch the scope segmented control to **Entire sequence**.
