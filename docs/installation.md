# Installation Guide — VoxForge Speech Enhancer Pro

This guide walks you through setting up VoxForge Speech Enhancer Pro in Adobe Premiere Pro on Windows.

---

## 1. System Requirements

| Component | Minimum | Recommended |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **Host Application** | Adobe Premiere Pro 2024 (v24.0+) | Adobe Premiere Pro 2025 (v25.5+) |
| **Processor (CPU)** | Intel Core i5 / AMD Ryzen 5 (4+ cores) | Intel Core i7-13620H / AMD Ryzen 7+ |
| **System Memory (RAM)** | 16 GB RAM | 32 GB – 64 GB RAM |
| **Graphics (GPU)** | Integrated Graphics (runs in CPU mode) | NVIDIA GeForce RTX 3060 / 4050 / 4060+ (6GB+ VRAM) |
| **CUDA Driver** | NVIDIA Driver 535+ (CUDA 12.0+) | NVIDIA Studio Driver 550+ |
| **Disk Space** | 2 GB for engine & models | 10 GB (for storage of model checkpoints and renders) |

---

## 2. One-Click Automated Installation

The fastest way to install VoxForge Pro into Adobe Premiere Pro is via the automated installation script:

1. Close Adobe Premiere Pro if it is currently open.
2. Open Windows File Explorer and navigate to the project directory:
   ```
   SpeechEnhancerPro\
   ```
3. Double-click **`install.bat`** (or right-click and choose **Run as administrator** if your `%APPDATA%` folder is write-protected).
4. The installer will automatically:
   - Create the external plugin directory at:
     ```
     %APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer
     ```
   - Deploy all UXP panel files (`manifest.json`, `index.html`, `main.css`, `index.js`, icons, and Premiere DOM bridge).
   - Detect and verify the local Python runtime with PyTorch and CUDA.
   - Verify the pre-installed neural model checkpoints in the model storage directory.

---

## 3. Automatic AI Engine Daemon Lifecycle

Speechify processes all audio locally on your machine using GPU acceleration. The engine is managed automatically by the extension:

1. When you open Speechify in Premiere Pro, the panel automatically starts the local background engine daemon silently without opening any terminal windows.
2. The engine reports readiness in the header (`Speechify ✓`).
3. When Premiere Pro or the Speechify panel is closed, the background engine automatically shuts down cleanly to release GPU resources.

---

## 4. Opening the Extension in Premiere Pro

1. Launch **Adobe Premiere Pro**.
2. Open your video project and active sequence.
3. In the Premiere Pro top menu bar, click:
   ```
   Window  ->  Extensions  ->  VoxForge Speech Enhancer Pro
   ```
4. The VoxForge Pro panel will open. You can dock it anywhere in your workspace (such as alongside the Audio Track Mixer or Essential Sound panel).
5. The status pill in the top header will glow green (**Engine Ready**), indicating the panel has connected to your local GPU daemon.

---

## 5. Configuring a Custom Model Storage Location

By default, models are stored in `SpeechEnhancerPro\models\storage`. You can easily relocate this to any fast NVMe drive or secondary storage:

1. In the VoxForge Pro panel header, click the **Settings (Gear)** icon.
2. In the **Unified Model Storage Directory** input field, enter your desired path (for example, `D:\AI_Weights\VoxForgeModels`).
3. Ensure the checkbox **"Automatically move existing models to the new location"** is checked.
4. Click **Save Path**.
5. The engine will instantly transfer your models to the new drive and update its configuration without requiring a restart.

---

## 6. Uninstalling

If you ever wish to remove the extension:
- Run `SpeechEnhancerPro\installers\uninstall.bat`.
- This removes the UXP panel from `%APPDATA%\Adobe\UXP\Plugins\External\com.voxforge.speechenhancer`.
- Your downloaded model checkpoints in `SpeechEnhancerPro\models\storage` are kept safe unless you choose to delete that folder manually.
