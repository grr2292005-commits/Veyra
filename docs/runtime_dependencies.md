# Speechify Runtime Dependencies Inventory

This document provides a comprehensive inventory of all runtime libraries, native toolchains, and model-specific dependencies required to operate Speechify locally and windowlessly inside Adobe Premiere Pro.

---

## 1. Core Python Runtime Environment

* **Runtime Type:** Private Embedded Virtual Environment (`runtime/`)
* **Base Python Version:** Python 3.11.9 (64-bit Windows)
* **Execution Binaries:** `runtime/Scripts/python.exe` (CLI/QA), `runtime/Scripts/pythonw.exe` (Windowless Background Engine)
* **Isolation Guarantee:** Zero dependency on system PATH `python.exe` or global `pip`.

| Dependency | Version | Purpose | Installation Mechanism | License | Bundled / Managed | Required For |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | 3.11.9 | Core runtime interpreter | Pre-packaged private runtime | PSF License | Bundled (`runtime/`) | All Subsystems |
| **PyTorch (`torch`)** | 2.6.0+cu124 | Neural tensor execution & GPU kernels | Managed PyTorch wheel with CUDA 12.4 | BSD-3-Clause | Bundled (`runtime/site-packages`) | All Models |
| **TorchVision** | 0.21.0+cu124 | Vision/spectral transforms | Managed wheel | BSD-3-Clause | Bundled (`runtime/site-packages`) | MP-SENet |
| **TorchAudio** | 2.6.0+cu124 | Audio I/O and transforms | Managed wheel | BSD-2-Clause | Bundled (`runtime/site-packages`) | Audio Pipeline |
| **SoundFile** | 0.12.1 | High-precision 24-bit PCM/Float WAV I/O | Managed wheel (includes libsndfile C-lib) | BSD-3-Clause | Bundled (`runtime/site-packages`) | Audio Pipeline |
| **NumPy** | 1.26.4 | Numerical array math & buffer operations | Exact locked wheel (ABI compatible) | BSD-3-Clause | Bundled (`runtime/site-packages`) | All Subsystems |
| **SciPy** | 1.17.1 | Polyphase sinc resampling (`resample_poly`) | Managed wheel | BSD-3-Clause | Bundled (`runtime/site-packages`) | Audio Pipeline |
| **ClearVoice** | 0.1.2 | MossFormerGAN inference pipeline | Managed wheel in private runtime | Apache 2.0 | Bundled (`runtime/site-packages`) | MossFormerGAN-SE |
| **Rotary-Embedding-Torch** | 0.8.3 | Rotary positional embeddings for attention | Managed wheel in private runtime | MIT | Bundled (`runtime/site-packages`) | MossFormerGAN-SE |
| **YAMLArgParse** | 1.31.1 | Model config YAML/JSON parser | Managed wheel in private runtime | MIT | Bundled (`runtime/site-packages`) | MossFormerGAN-SE |
| **DeepFilterNet** | 0.5.6 | ERB deep filtering model & Rust backend | Managed wheel / crate | MIT / Apache 2.0 | Bundled (`runtime/site-packages`) | DeepFilterNet3 |
| **Psutil** | 7.2.2 | Process tracking & memory leak detection | Managed wheel | BSD-3-Clause | Bundled (`runtime/site-packages`) | Engine Lifecycle |

---

## 2. Hardware Acceleration & CUDA Runtime

| Component | Target Version | Purpose | Fallback Behavior |
| :--- | :--- | :--- | :--- |
| **NVIDIA CUDA Toolkit** | 12.4 (Bundled in PyTorch wheels) | Tensor cores & CUDA GEMM execution | Automatic fallback to CPU if CUDA is unavailable or VRAM is low |
| **cuDNN** | 9.x (Bundled in PyTorch wheels) | Deep neural network convolutions & RNNs | CPU vectorized kernels |

---

## 3. Audio Extraction & Codec Tools

* **Libsndfile:** Embedded inside the `soundfile` Python wheel.
* **FFmpeg:** Optional system extraction tool. For standard broadcast WAV, MP3, and timeline audio, Speechify uses libsndfile and Premiere Pro's native audio composite engine, eliminating mandatory user FFmpeg installation.

---

## 4. Licensing Compliance Audit

All dependencies adhere to permissive open-source licenses (BSD, MIT, Apache 2.0, PSF). There are no GPL or copyleft runtime components bundled with Speechify that would restrict commercial post-production or enterprise Premiere Pro distribution.
