/**
 * Speechify — Authoritative Application State Store
 * Single source of truth for engine, hardware, model storage, models,
 * processing device, Premiere timeline, and user settings.
 */

(function (global) {
  'use strict';

  class AppStateStore {
    constructor() {
      this._state = {
        engine: {
          status: "stopped", // 'stopped' | 'starting' | 'ready' | 'error' | 'restarting'
          pid: null,
          port: 8765,
          version: "1.0.0",
          error: null,
          lastHealth: null
        },
        hardware: {
          cpu: "Detecting CPU...",
          ramGB: 0,
          gpu: null,
          gpus: [],
          backends: { cpu: true, cuda: false },
          tier: "B",
          tierName: ""
        },
        modelStorage: {
          path: "",
          rawPath: "",
          isManaged: true,
          displayTitle: "Speechify managed storage",
          displaySubtext: "Models are stored locally on this computer.",
          accessible: true,
          error: null,
          modelsCount: 0
        },
        models: {},
        processingDevice: {
          mode: "auto", // 'auto' | 'cuda' | 'cpu'
          resolvedDevice: "cpu",
          availableDevices: [
            { id: "auto", name: "Automatic (Recommended)", type: "auto" },
            { id: "cpu", name: "CPU — System Processor", type: "cpu" }
          ]
        },
        premiere: {
          activeSequence: null,
          selectedClips: [],
          scope: "selected_clips", // 'selected_clips' | 'in_out' | 'full_sequence'
          selectedTrackIds: []
        },
        settings: {
          normalize: false,
          placementMode: "new_track"
        }
      };

      this._listeners = new Map(); // slice -> Set of callback functions
    }

    get state() {
      return this._state;
    }

    get engine() {
      return this._state.engine;
    }

    get hardware() {
      return this._state.hardware;
    }

    get modelStorage() {
      return this._state.modelStorage;
    }

    get models() {
      return this._state.models;
    }

    get processingDevice() {
      return this._state.processingDevice;
    }

    get premiere() {
      return this._state.premiere;
    }

    get settings() {
      return this._state.settings;
    }

    subscribe(slice, callback) {
      if (typeof slice === 'function') {
        callback = slice;
        slice = '*';
      }
      if (!this._listeners.has(slice)) {
        this._listeners.set(slice, new Set());
      }
      this._listeners.get(slice).add(callback);
      // Return unsubscription function
      return () => {
        const sliceListeners = this._listeners.get(slice);
        if (sliceListeners) {
          sliceListeners.delete(callback);
        }
      };
    }

    _notify(slice) {
      if (this._notifyingSlices && this._notifyingSlices.has(slice)) {
        return; // Re-entrancy guard: prevent infinite recursion on the same slice
      }
      if (!this._notifyingSlices) this._notifyingSlices = new Set();
      this._notifyingSlices.add(slice);

      try {
        const sliceListeners = this._listeners.get(slice);
        if (sliceListeners) {
          sliceListeners.forEach(cb => {
            try {
              cb(this._state[slice], this._state);
            } catch (err) {
              console.warn(`[AppState] Listener error on slice '${slice}':`, err);
            }
          });
        }
        // Also notify wildcards
        const globalListeners = this._listeners.get('*');
        if (globalListeners) {
          globalListeners.forEach(cb => {
            try {
              cb(this._state, slice, this._state[slice]);
            } catch (err) {
              console.warn(`[AppState] Global listener error:`, err);
            }
          });
        }
      } finally {
        this._notifyingSlices.delete(slice);
      }
    }

    setEngine(patch) {
      let changed = false;
      for (const k in patch) {
        if (this._state.engine[k] !== patch[k]) {
          this._state.engine[k] = patch[k];
          changed = true;
        }
      }
      if (changed) this._notify('engine');
    }

    setEngineStatus(status, detail = {}) {
      let changed = (this._state.engine.status !== status);
      this._state.engine.status = status;
      if (detail.error !== undefined && this._state.engine.error !== detail.error) {
        this._state.engine.error = detail.error;
        changed = true;
      }
      if (detail.pid !== undefined && this._state.engine.pid !== detail.pid) {
        this._state.engine.pid = detail.pid;
        changed = true;
      }
      if (detail.lastHealth !== undefined) {
        this._state.engine.lastHealth = detail.lastHealth;
      }
      if (changed) this._notify('engine');
    }

    setHardware(patch) {
      Object.assign(this._state.hardware, patch);
      this._notify('hardware');
    }

    setModelStorage(patch) {
      Object.assign(this._state.modelStorage, patch);
      this._notify('modelStorage');
    }

    setModels(modelsMap) {
      this._state.models = Object.assign({}, modelsMap);
      const installedCount = Object.values(this._state.models).filter(m => m.installed).length;
      this._state.modelStorage.modelsCount = installedCount;
      this._notify('models');
      this._notify('modelStorage');
    }

    setProcessingDevice(patch) {
      if (typeof patch === 'string') {
        patch = { mode: patch };
      }
      Object.assign(this._state.processingDevice, patch);
      this._notify('processingDevice');
    }

    setAvailableDevices(devices) {
      if (!Array.isArray(devices)) return;
      this._state.processingDevice.availableDevices = devices;
      this._notify('processingDevice');
    }

    setSelectedTrackIds(trackIds) {
      this._state.premiere.selectedTrackIds = Array.isArray(trackIds) ? trackIds : [];
      this._notify('premiere');
    }

    setPremiere(patch) {
      Object.assign(this._state.premiere, patch);
      this._notify('premiere');
    }

    setSettings(patch) {
      Object.assign(this._state.settings, patch);
      this._notify('settings');
    }
  }

  global.SpeechifyAppState = new AppStateStore();

})(typeof window !== 'undefined' ? window : global);
