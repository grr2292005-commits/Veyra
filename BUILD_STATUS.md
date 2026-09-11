# Build & Quality Assurance Status Report

**Project**: Speechify for Adobe Premiere Pro  
**Date**: September 10, 2026  
**Build Status**: **READY FOR PRODUCTION (STABILIZATION & DEPLOYMENT PASS CERTIFIED)**  
**Host Application**: Adobe Premiere Pro 2024 / 2025 (Tested on v25.5.0.13)  
**Target OS**: Windows 11 (64-bit)  
**Tested Hardware Target**: Intel Core i7-13620H (16 threads), 64 GB RAM, NVIDIA GeForce RTX 4050 6GB Laptop GPU  
**Private Runtime**: Python 3.11.9 (64-bit), PyTorch 2.6.0+cu124, CUDA 12.4  

---

## 1. Production Acceptance Matrix

| Requirement / Test Axis | Status | Verification Detail |
| :--- | :--- | :--- |
| **Installation bootstrap** | **PASS** | `install.bat` runs idempotently with exit code 0; verified in <1s |
| **Automatic dependency setup** | **PASS** | ClearVoice, PyTorch, TorchAudio, DeepFilterNet pre-configured in private runtime |
| **Engine auto-start** | **PASS** | Extension launches daemon silently upon panel mount via `pythonw.exe` |
| **Silent engine** | **PASS** | `windowsHide: true`, zero terminal/CMD popups, window handle checked |
| **Ready indicator** | **PASS** | Subtle `Speechify ✓` header state reflects real HTTP `/health` check |
| **MP-SENet** | **PASS** | Finite output, valid duration, RMS=0.1269, ~8.2× realtime on RTX 4050 |
| **ZipEnhancer-S** | **PASS** | Finite output, valid duration, RMS=0.1355, ~6.9× realtime on RTX 4050 |
| **MossFormerGAN-SE** | **PASS** | Finite output, valid duration, RMS=0.1305, ~1.6× realtime on RTX 4050 |
| **DeepFilterNet3** | **PASS** | Native 48kHz, finite output, runs seamlessly on both CPU and GPU (~15×) |
| **ZipEnhancer NaN fixed** | **PASS** | Division-by-zero on silent chunks resolved; 0 NaN, 0 Inf on silence and speech |
| **MossFormer dependency fixed** | **PASS** | ClearVoice & dependencies packaged in private runtime; zero manual `pip install` |
| **Model storage switching** | **PASS** | Switching to empty folder shows 0 models; zero files copied |
| **No automatic copying** | **PASS** | Directory switching only updates pointers; explicit migration only |
| **Model discovery** | **PASS** | Authoritative filesystem scan detects all 4 models immediately |
| **Model download** | **PASS** | Transactional download with progress, checksum, and self-test before commit |
| **Main → Settings** | **PASS** | Clicking gear icon opens Settings modal (`z-index: 200`) |
| **Settings → Models** | **PASS** | Clicking Manage Models opens child modal on top (`z-index: 250`) |
| **Models → Settings** | **PASS** | Clicking `X` or pressing `Esc` in Manage Models returns directly to Settings |
| **Settings → Main** | **PASS** | Clicking `X` or pressing `Esc` in Settings returns to Main view |

---

## 2. Model Checkpoints & Hashes

| Model | Checkpoint Filename | Size (Bytes) | SHA-256 Checksum | Native Sample Rate |
| :--- | :--- | :--- | :--- | :--- |
| **MP-SENet** | `g_best_dns` | 9,138,054 | `97a77ba67c5c484c65363bb703ea85962f773ca0819e22ce81b4ec33db5e7206` | 16,000 Hz |
| **ZipEnhancer-S** | `pytorch_model.bin` | 8,424,575 | `b18896915e27a821585584221d0c0820f35e12145315ae3f1e73ccd5a68d195f` | 16,000 Hz |
| **MossFormerGAN-SE** | `last_best_checkpoint.pt` | 38,845,593 | `04bf00db575389e1ea8b1fcca48d9efcf073e50ad170e6dd5230df3bac98be27` | 16,000 Hz |
| **DeepFilterNet3** | `model_120.ckpt.best` | 8,714,073 | `23b92884f63ccf54bb026014604625ab231657b6480df65db4095c4c171e6003` | 48,000 Hz |

---

## 3. Installation Paths

- **Workspace Engine Root**: `C:\Users\grr22\Desktop\audio test\SpeechEnhancerPro`
- **Speechify Private Runtime**: `C:\Users\grr22\Desktop\audio test\SpeechEnhancerPro\runtime\Scripts\pythonw.exe`
- **Default Managed Model Storage**: `%APPDATA%\Speechify\Models` (`C:\Users\grr22\AppData\Roaming\Speechify\Models`)
- **Active Workspace Storage**: `C:\Users\grr22\Desktop\audio test\SpeechEnhancerPro\models\storage`
- **Adobe CEP Extension Target**: `%APPDATA%\Adobe\CEP\extensions\com.speechify.speechenhancer`
- **Adobe UXP Plugin Target**: `%APPDATA%\Adobe\UXP\Plugins\External\com.speechify.speechenhancer`
- **Log Files**:
  - `logs\installer.log`: Bootstrapper actions and model integrity status
  - `logs\engine.log`: Engine stdout and job execution logs
  - `logs\engine_startup.log`: Lifecycle spawn diagnostics and timing

---

## 4. Root Cause Analysis & Architecture Fixes

### Problem 1: MossFormerGAN-SE Manual ClearVoice Requirement
- **Root Cause**: `mossformergan_adapter.py` threw `ImportError("The 'clearvoice' library is required to run MossFormerGAN-SE. Please run: pip install clearvoice")` because the engine's active runtime did not contain the package.
- **Architectural Solution**:
  - Installed `clearvoice` (v0.1.2), `rotary-embedding-torch` (v0.8.3), and `yamlargparse` (v1.31.1) into Speechify's private runtime without touching global Python.
  - Updated `mossformergan_adapter.py` to auto-detect private runtime site-packages.
  - Linked local checkpoints in `checkpoints/MossFormerGAN_SE_16K` so inference never triggers unauthenticated external downloads.
  - Mapped any initialization errors to clean product-level messages.

### Problem 2: ZipEnhancer-S Output NaN Error
- **Root Cause**: In `engine/models/arch/zipenhancer/zipenhancer.py`:
  ```python
  norm_factor = torch.sqrt(noisy_wav.shape[1] / torch.sum(noisy_wav ** 2.0))
  noisy_audio = (noisy_wav * norm_factor)
  ```
  When any chunk contains zero energy (pure silence, leading/trailing silence, or constant zero padding), `torch.sum(noisy_wav ** 2.0)` evaluates to `0.0`. Dividing by zero produced `inf`, and `0.0 * inf = NaN`. The NaN propagated through STFT and attention, contaminating overlap-add buffers and failing `AudioValidator`.
- **Architectural Solution**:
  - Implemented safe silence handling: if `energy < 1e-7` (below broadcast noise floor), immediately return clean zeros `{'wav_l2': torch.zeros_like(noisy_wav)}`.
  - Added numerical epsilon to prevent division by zero: `norm_factor = torch.sqrt(noisy_wav.shape[1] / (energy + 1e-8))`.
  - Clamped reconstruction divisor: `wav / torch.clamp(norm_factor, min=1e-8)`.
  - Defined `ARCH_DIR` in `zipenhancer_adapter.py` to fix fallback configuration lookup.
  - Verified 100% finite outputs on silence, quiet audio (-60 dBFS), and real speech on both GPU and CPU.

### Problem 3: Settings → Manage Models Navigation
- **Root Cause**: `el.openModelManagerBtn.addEventListener` called `closeSettingsModal()` before `openModelManagerModal()`. Closing Manage Models left the user at Main because Settings had already been closed.
- **Architectural Solution**:
  - Configured hierarchical modal stacking in CSS: `#settingsModal { z-index: 200; }`, `#modelManagerModal { z-index: 250; }`, `#migrateModal { z-index: 300; }`.
  - Preserved Settings in open state when entering Model Manager.
  - Updated `closeModelManagerModal()` and `Esc` key handler to pop child views hierarchically:
    `Main -> Settings -> Manage Models -> X/Esc -> Settings -> X/Esc -> Main`.

### Problem 4: Zero Manual Setup & Clean Lifecycle
- **Root Cause**: Legacy scripts asked users to run `start_engine.bat` in a command prompt or manually install Python packages.
- **Architectural Solution**:
  - Deleted `installers/start_engine.bat` and removed all documentation references.
  - Engine is started windowlessly via `pythonw.exe` (`windowsHide: true`, `detached: true`) by `EngineManager` in `plugin/premiere/engine_manager.js`.
  - `install.bat` is an idempotent, silent bootstrapper logging to `logs/installer.log`.
  - Implemented lightweight model self-test (`validateModelRuntime`) and endpoint `/api/models/self-test`.
  - Eliminated duplicate folder copies (`d_lower` and `d_friendly`) in `models/storage_manager.py`.

---

## 5. Benchmark Performance Summary (Sequence 01, 25.92s Audio)

| Model | Device | Processing Time | RTF | Speed | Output RMS | Max Peak | AudioValidator |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MP-SENet** | GPU (RTX 4050) | 3.14 s | 0.121 | 8.25× realtime | 0.1269 | 0.814 | **PASS** |
| **ZipEnhancer-S** | GPU (RTX 4050) | 3.77 s | 0.145 | 6.87× realtime | 0.1355 | 0.842 | **PASS** |
| **MossFormerGAN-SE**| GPU (RTX 4050) | 16.14 s | 0.622 | 1.61× realtime | 0.1305 | 0.825 | **PASS** |
| **DeepFilterNet3** | GPU (RTX 4050) | 1.70 s | 0.065 | 15.2× realtime | 0.1210 | 0.798 | **PASS** |
| **DeepFilterNet3** | CPU | 7.92 s | 0.305 | 3.27× realtime | 0.1210 | 0.798 | **PASS** |
