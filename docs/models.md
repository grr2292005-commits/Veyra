# Model Specification & Benchmark Guide — VoxForge Pro

VoxForge Speech Enhancer Pro integrates 4 state-of-the-art open-source neural speech enhancement architectures. Each model has been evaluated, benchmarked, and optimized for local Windows execution on NVIDIA GeForce RTX hardware.

---

## 1. Comparative Performance Matrix (RTX 4050 6GB Benchmark)

All benchmark figures were measured on a **25.92-second 48kHz dialogue recording (`Sequence 01.mp3`)** on an Intel Core i7-13620H system with NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM) running PyTorch 2.6.0+cu124:

| Feature / Metric | MP-SENet | ZipEnhancer-S | DeepFilterNet3 | MossFormerGAN-SE |
| :--- | :--- | :--- | :--- | :--- |
| **Category** | **High Quality (Lead)** | **Balanced Efficiency** | **Ultra-Fast / CPU** | **Studio Quality (Heavy)** |
| **Processing Time (26s audio)** | **3.14 seconds** | **3.77 seconds** | **1.70 seconds** | 16.14 seconds |
| **Speed Multiplier** | **8.25× Realtime** | **6.87× Realtime** | **15.2× Realtime** | 1.61× Realtime |
| **Real-Time Factor (RTF)** | **0.121** | **0.146** | **0.065** | 0.623 |
| **Peak GPU VRAM** | **537 MB** | **305 MB** | **150 MB (or 0 MB CPU)**| 4,469 MB (~4.5 GB) |
| **Speech Quality Score** | ★★★★★ (5.0 / 5) | ★★★★½ (4.5 / 5) | ★★★★☆ (4.0 / 5) | ★★★★★ (5.0 / 5) |
| **Native Model Sample Rate** | 16,000 Hz | 16,000 Hz | 48,000 Hz (Native) | 16,000 Hz |
| **Parameters** | 2.26 Million | 2.04 Million | 2.14 Million | 3.13 Million |
| **Checkpoint Size** | 9.1 MB | 8.4 MB | 8.5 MB | 38.8 MB |
| **Recommended Hardware** | RTX 3050 / 4050 / 4060+ | Low-VRAM GPU (2–4GB) | Any CPU or Entry GPU | High-VRAM GPU (8GB+) |
| **License** | MIT License | Apache 2.0 | MIT License | Apache 2.0 |

---

## 2. Deep Technical Breakdown

### 1. MP-SENet (Recommended Default for RTX 4050)
* **Full Title**: *Explicit Estimation of Magnitude and Phase Spectra in Parallel for High-Quality Speech Enhancement* (Interspeech / IEEE/ACM TASLP).
* **Core Innovation**: Traditional speech enhancement models only estimate spectral magnitude (spectral subtraction/masking) and reuse noisy phase, which produces metallic artifacts, phase cancellation, and robotic flutter. MP-SENet uses parallel Time-Frequency Transformers to reconstruct the complex phase spectrum alongside magnitude simultaneously.
* **Acoustic Characteristics**: Natural voice contours, intact high-frequency fricatives ('s', 'f', 'th'), crisp vocal presence, and complete removal of background HVAC/room noise.
* **VRAM Optimization**: Implemented with a **2.0-second Hann overlap-add window (50% overlap)**. This ensures that memory consumption remains strictly capped at **~537 MB**, completely preventing self-attention out-of-memory errors on long audio files.

---

### 2. ZipEnhancer-S (Balanced Alternative)
* **Full Title**: *ZipEnhancer: Dual-Path Down-Up Sampling-based Zipformer for Monaural Speech Enhancement* (ICASSP 2025).
* **Core Innovation**: Built upon the Zipformer architecture developed by the speech research community. Employs hierarchical downsampling and upsampling in the time domain with BiasNorm and Non-Linear Attention mechanisms, reducing attention computational complexity by 4×.
* **Acoustic Characteristics**: Warm, broadcast-style dialogue cleanup with exceptional smoothness. Very gentle on vocal sibilance, making it ideal for voices with harsh high frequencies.
* **VRAM Optimization**: Implemented with a **1.0-second Hann overlap-add window (50% overlap)**. Peak VRAM consumption is only **~305 MB**, making it safe even when 3D animation, video effects, or multiple monitors are sharing GPU memory.

---

### 3. DeepFilterNet3 (Ultra-Fast Full-Band & CPU Fallback)
* **Full Title**: *DeepFilterNet: A Low-Complexity Speech Enhancement Framework for Full-Band Audio* (IEEE TASLP).
* **Core Innovation**: Operates directly at **48,000 Hz full-band audio** using complex Equivalent Rectangular Bandwidth (ERB) filter banks. Instead of traditional resampling to 16kHz, DeepFilterNet3 processes speech at native studio sample rate with deep complex filtering.
* **Acoustic Characteristics**: Ultra-fast, clean broadband noise suppression. Extremely reliable for draft editorial passes, dialogue logging, and battery-powered laptop editing.
* **VRAM & CPU**: Uses only **150 MB VRAM** on GPU, and runs at **~3.2× realtime on pure CPU** with zero dedicated GPU requirements.

---

### 4. MossFormerGAN-SE (Deep Studio Restoration)
* **Full Title**: *ClearerVoice-Studio: An Open-Source Processing Suite for Speech Enhancement, Separation, and Dereverberation* (arXiv:2407.03901).
* **Core Innovation**: Features the MossFormer recurrent self-attention backbone coupled with dual spectral and masking decoders trained with an adversarial GAN loss.
* **Acoustic Characteristics**: Superb high-treble speech clarity and aggressive attenuation of challenging non-stationary noises (e.g. coffee shop clatter, outdoor wind, passing vehicles).
* **Hardware Warning**: Requires **~4.5 GB peak VRAM**. On 6GB GPUs like the RTX 4050 Laptop, it runs successfully (16s for 26s audio) but leaves limited headroom for Premiere Pro's Mercury Playback Engine. Recommended primarily for workstations with 8GB+ dedicated VRAM.
