# Speechify Model Inventory & Checkpoint Registry

This document catalogues all neural speech enhancement models integrated into Speechify, their exact checkpoint metadata, hardware requirements, runtime dependencies, and licensing terms.

---

## Model Matrix

| Model | Category | Sample Rate | Params | Checkpoint File | Checkpoint Size | Device Support | Primary License | Upstream Source |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MP-SENet** | Studio / Narration | 16,000 Hz | 2.26 M | `g_best_dns` | 9.14 MB | GPU (CUDA) + CPU | MIT | [JacobLinCool/MP-SENet-DNS](https://huggingface.co/JacobLinCool/MP-SENet-DNS) |
| **ZipEnhancer-S** | Balanced Dialogue | 16,000 Hz | 2.04 M | `pytorch_model.bin` | 8.42 MB | GPU (CUDA) + CPU | Apache 2.0 | [ModelScope iic/speech_zipenhancer](https://www.modelscope.cn/models/iic/speech_zipenhancer_ans_multiloss_16k_base) |
| **MossFormerGAN-SE** | Heavy Noise / Studio | 16,000 Hz | 3.13 M | `last_best_checkpoint.pt` | 38.85 MB | Dedicated GPU (CUDA) | Apache 2.0 | [alibabasglab/MossFormerGAN_SE_16K](https://huggingface.co/alibabasglab/MossFormerGAN_SE_16K) |
| **DeepFilterNet3** | Ultra Fast / CPU | 48,000 Hz | 2.14 M | `model_120.ckpt.best` | 8.54 MB | CPU + GPU (CUDA) | MIT | [Rikorose/DeepFilterNet v0.5.6](https://github.com/Rikorose/DeepFilterNet) |

---

## Detailed Model Profiles

### 1. MP-SENet (Magnitude and Phase Estimation Network)
* **Architecture:** Dual-Path Time-Frequency Conformer with parallel magnitude and phase estimation heads.
* **Checkpoint Hash (SHA-256):** `4c45bb22b10a9c68705f4e69b5962b704c351c911b33e9d8926eaebcbb7cf61d`
* **Audio Characteristics:** Eliminates phase-cancellation flutter and metallic/robotic artifacts. Natural voice contours, high speech intelligibility, crisp consonants.
* **Resource Footprint:**
  * VRAM: ~537 MB on GPU
  * RAM: ~1.2 GB
  * Realtime Factor (RTF): ~0.121 (8.25× realtime on RTX 4050)
* **Recommended For:** Professional narration, voice-over, commercial dialogue, podcast host tracks.

### 2. ZipEnhancer-S (Dual-Path Down-Up Sampling Zipformer)
* **Architecture:** ICASSP 2025 Zipformer backbone with BiasNorm, Non-Linear Attention, and multi-loss objectives.
* **Checkpoint Hash (SHA-256):** `472dd962b16df3d158fa9960251147a27eb255b774c86b24ae30815450fdf588`
* **Numerical Hardening:** Division-by-zero on silent chunks resolved via strict epsilon (`1e-8`) and energy thresholding (< 1e-7 RMS). 100% NaN/Inf free.
* **Resource Footprint:**
  * VRAM: ~305 MB on GPU
  * RAM: ~1.1 GB
  * Realtime Factor (RTF): ~0.145 (6.87× realtime on RTX 4050)
* **Recommended For:** General dialogue, YouTube content, long interviews, low-VRAM GPUs.

### 3. MossFormerGAN-SE (Adversarial Dual-Decoder)
* **Architecture:** MossFormer attention module with dual spectral and masking decoders trained with GAN discriminators.
* **Checkpoint Hash (SHA-256):** `3cb49a4f4d2f0d9ff4a19b222956cf57422f28cfdfab805b8ffce16e885c07b0`
* **Runtime Dependencies:** `clearvoice` (v0.1.2), `rotary-embedding-torch` (v0.8.3), `yamlargparse` (v1.31.1). Managed entirely within private runtime.
* **Resource Footprint:**
  * VRAM: ~4.47 GB on GPU (requires >= 4GB VRAM)
  * RAM: ~2.2 GB
  * Realtime Factor (RTF): ~0.622 (1.61× realtime on RTX 4050)
* **Recommended For:** Difficult acoustic environments, heavy street/restaurant noise, high-treble vocal cleanup.

### 4. DeepFilterNet3 (Fullband 48kHz Deep Filtering)
* **Architecture:** Deep filtering on complex ERB bands with gated convolutional recurrent units (GRU).
* **Native Sample Rate:** 48,000 Hz (zero downsampling required for broadcast video).
* **Resource Footprint:**
  * VRAM: ~150 MB on GPU (0 MB on CPU)
  * RAM: ~600 MB
  * Realtime Factor (RTF): ~0.065 (15.2× realtime on GPU, ~3× on CPU)
* **Recommended For:** Laptops on battery, CPU-only systems, rapid drafts, background speech cleanup.
