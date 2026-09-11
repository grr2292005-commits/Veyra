/**
 * Speechify — Authoritative Hardware Manager
 * Queries engine /api/system, parses GPU/CPU profiles, and manages available device models.
 * Guarantees that hardware state is independent of model selection and always synchronized with AppState.
 */

(function (global) {
  'use strict';

  class HardwareManager {
    constructor() {
      this._profile = null;
      this._availableDevices = [
        { id: "auto", name: "Automatic (Recommended)", label: "Automatic (Recommended)", type: "auto", available: true },
        { id: "cpu", name: "CPU — System Processor", label: "CPU — System Processor", type: "cpu", available: true }
      ];
      this._selectedDeviceId = "auto";
      this._isDetecting = false;
      this._lastError = null;
      this._detectTimeoutMs = 4000;
    }

    /**
     * Authoritative query against backend engine for hardware capabilities.
     * Logs output at each stage for full traceability.
     */
    async detect(engineUrl = "http://127.0.0.1:8765") {
      this._isDetecting = true;
      console.log(`[HardwareManager] 1. Initiating hardware detection from engine at: ${engineUrl}/api/system`);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this._detectTimeoutMs);

      try {
        const resp = await fetch(`${engineUrl}/api/system`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!resp.ok) {
          throw new Error(`Engine returned HTTP ${resp.status} ${resp.statusText}`);
        }

        const profile = await resp.json();
        this._profile = profile;
        this._lastError = null;

        console.log(`[HardwareManager] 2. Received hardware profile:`, {
          os: profile.os,
          cpu: profile.cpu ? profile.cpu.name : "N/A",
          gpu_count: (profile.gpus ? profile.gpus.length : (profile.gpu && profile.gpu.available ? 1 : 0)),
          gpu_name: profile.gpu ? profile.gpu.name : "None",
          recommendedDevice: profile.recommendedDevice
        });

        // 3. Build authoritative available device list
        const devices = [];

        // Always provide Automatic (Recommended)
        devices.push({
          id: "auto",
          name: "Automatic (Recommended)",
          label: "Automatic (Recommended)",
          type: "auto",
          available: true
        });

        // Add detected GPUs from profile
        if (profile.available_devices && Array.isArray(profile.available_devices) && profile.available_devices.length > 0) {
          // If backend provided pre-formatted available_devices, use them
          profile.available_devices.forEach(dev => {
            if (dev.id !== "auto" && dev.id !== "cpu") {
              devices.push({
                id: dev.id,
                name: dev.name || dev.label,
                label: dev.label || dev.name,
                type: dev.type || "cuda",
                available: dev.available !== undefined ? dev.available : true,
                vramGB: dev.vramGB || (dev.vram_gb ? Math.round(dev.vram_gb) : 0),
                vram_gb: dev.vram_gb || dev.vramGB || 0
              });
            }
          });
        } else if (profile.gpus && Array.isArray(profile.gpus) && profile.gpus.length > 0) {
          profile.gpus.forEach((gpu, idx) => {
            if (gpu.available || gpu.cuda || gpu.cuda_available) {
              const rawName = gpu.name || gpu.device_name || `GPU ${idx}`;
              const cleanName = rawName.replace("NVIDIA GeForce ", "NVIDIA ").replace(" Laptop GPU", "");
              const vram = Math.round(gpu.total_vram_gb || gpu.vramGB || 6);
              const devId = gpu.id || `cuda:${idx}`;
              const label = `GPU — ${cleanName} (${vram} GB VRAM)`;
              devices.push({
                id: devId,
                name: label,
                label: label,
                type: "cuda",
                available: true,
                vramGB: vram,
                vram_gb: gpu.total_vram_gb || vram
              });
            }
          });
        } else if (profile.gpu && (profile.gpu.available || profile.gpu.cuda || profile.gpu.cuda_available)) {
          const rawName = profile.gpu.name || profile.gpu.device_name || "NVIDIA GPU";
          const cleanName = rawName.replace("NVIDIA GeForce ", "NVIDIA ").replace(" Laptop GPU", "");
          const vram = Math.round(profile.gpu.total_vram_gb || profile.gpu.vramGB || 6);
          const devId = profile.gpu.id || "cuda:0";
          const label = `GPU — ${cleanName} (${vram} GB VRAM)`;
          devices.push({
            id: devId,
            name: label,
            label: label,
            type: "cuda",
            available: true,
            vramGB: vram,
            vram_gb: profile.gpu.total_vram_gb || vram
          });
        }

        // Add CPU option from backend profile if available, or fallback
        const backendCpu = profile.available_devices ? profile.available_devices.find(d => d.id === "cpu") : null;
        const cpuLabel = backendCpu ? (backendCpu.label || backendCpu.name) : "CPU — System Processor";
        devices.push({
          id: "cpu",
          name: cpuLabel,
          label: cpuLabel,
          type: "cpu",
          available: true
        });

        this._availableDevices = devices;
        console.log(`[HardwareManager] 3. Authoritative devices built (${devices.length} options):`, devices.map(d => d.name));

        // 4. Propagate to AppState
        if (global.SpeechifyAppState) {
          global.SpeechifyAppState.setHardware(profile);
          global.SpeechifyAppState.setAvailableDevices(devices);
          console.log(`[HardwareManager] 4. Successfully propagated devices to SpeechifyAppState.`);
        }

        return devices;
      } catch (err) {
        clearTimeout(timeoutId);
        console.warn(`[HardwareManager] Hardware detection failed:`, err);
        this._lastError = err;

        // Propagate fallback to AppState so UI stays stable
        if (global.SpeechifyAppState) {
          global.SpeechifyAppState.setAvailableDevices(this._availableDevices);
        }
        return this._availableDevices;
      } finally {
        this._isDetecting = false;
      }
    }

    /**
     * Authoritative list of devices available on this host.
     */
    getAvailableDevices() {
      return this._availableDevices;
    }

    /**
     * Full raw system hardware profile from engine.
     */
    getProfile() {
      return this._profile;
    }

    isDetecting() {
      return this._isDetecting;
    }

    getLastError() {
      return this._lastError;
    }

    getSelectedDevice() {
      return this._selectedDeviceId;
    }

    setSelectedDevice(deviceId) {
      this._selectedDeviceId = deviceId;
      try {
        localStorage.setItem('speechify_device_preference', deviceId);
      } catch (e) {}

      if (global.SpeechifyAppState) {
        global.SpeechifyAppState.setProcessingDevice({ mode: deviceId });
      }
      console.log(`[HardwareManager] Selected processing device set to: ${deviceId}`);
    }
  }

  global.SpeechifyHardwareManager = new HardwareManager();

})(typeof window !== 'undefined' ? window : global);
