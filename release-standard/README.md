# Veyra — Standard Release
### Local AI Speech Enhancement for Adobe Premiere Pro

Veyra is a high-performance, 100% offline neural speech enhancement extension for Adobe Premiere Pro (2024 & 2025). This standard release provides a lightweight (~1 MB) installer that automatically configures an optimized, hardware-aware private Python runtime on your system without manual configuration.

---

## Features

- **Ultralight Package**: Standard installer download is under 2 MB.
- **Hardware-Aware AI Acceleration**: Automatically detects your hardware and installs NVIDIA CUDA-accelerated PyTorch (if supported) or an optimized multi-core CPU runtime.
- **100% Automated Setup**: No manual Python, pip, CUDA, or FFmpeg installation required.
- **On-Demand Model Downloads**: Downloads only the neural speech enhancement models you choose directly inside the extension settings or timeline.
- **Non-Destructive Workflow**: Places enhanced audio onto dedicated, non-overlapping audio tracks in Adobe Premiere Pro.

---

## System Requirements

- **Operating System**: Windows 10 / 11 (64-bit)
- **Host Application**: Adobe Premiere Pro 2024 (v24.0+) or 2025 (v25.0+)
- **GPU (Recommended)**: NVIDIA RTX / GTX GPU with 4GB+ VRAM (CUDA compatible) or modern multi-core x64 CPU
- **RAM**: 8 GB minimum (16 GB recommended)
- **Internet**: Required during initial setup to download runtime dependencies and AI models.

---

## Installation

1. Close Adobe Premiere Pro if it is running.
2. Run **`Veyra-Setup.exe`**.
3. The automated installer will:
   - Detect your system hardware and compute capabilities.
   - Set up an isolated private runtime in `%LOCALAPPDATA%\Veyra\runtime`.
   - Install hardware-matched dependencies (CUDA or CPU PyTorch).
   - Deploy the extension to Adobe Premiere Pro.
   - Verify that the local engine can start and self-test.
4. Launch Adobe Premiere Pro.
5. In Premiere Pro, open the extension via:
   **Window → Extensions → Veyra**

---

## Basic Usage

1. Open your project sequence in Adobe Premiere Pro.
2. Select one or more dialogue clips on the timeline (or select an audio track).
3. Open the **Veyra** panel.
4. Choose your preferred AI Model (e.g. MP-SENet, ZipEnhancer-S, DeepFilterNet3, MossFormerGAN-SE).
5. Click **Enhance Speech**. Models are automatically downloaded on first use if not already present.
6. The enhanced audio is placed onto a dedicated track in your timeline.

---

## Uninstallation

Run **`Veyra-Uninstall.exe`**. Your projects, sequence timelines, and downloaded models remain completely safe.

---

## Portable / Offline Release

For air-gapped computers or completely offline environments without internet access, use the **Veyra Portable Release** (`release-portable`), which bundles the complete Python environment and all four neural model checkpoints pre-installed.

---

## License

Veyra is licensed under the Apache License, Version 2.0. Neural model checkpoints are subject to their respective open-source licenses (MIT and Apache 2.0). See [LICENSE](LICENSE) for details.
