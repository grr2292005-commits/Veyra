/**
 * Speechify — Storage & Filesystem Service
 * Single authority for model storage location, folder picking (UXP/CEP),
 * transactional directory switching, and model state synchronization.
 */

(function (global) {
  'use strict';

  const nodeRequire = (typeof window !== 'undefined' && window.require)
    ? window.require
    : (typeof require !== 'undefined' ? require : null);

  const fs = nodeRequire ? nodeRequire('fs') : null;

  class StorageService {
    constructor() {
      this.baseUrl = "http://127.0.0.1:8765";
    }

    /**
     * Initializes storage state from backend or defaults.
     * Guaranteed to never throw uncaught exceptions and never leave storage empty.
     */
    async init() {
      // 1. Resolve default local managed directory first
      let defaultPath = "";
      try {
        if (global.SpeechifyPathManager) {
          const paths = global.SpeechifyPathManager.getPaths();
          if (paths && paths.defaultModelStorage) {
            defaultPath = paths.defaultModelStorage;
          }
        }
      } catch (e) {}

      // Immediately seed AppState with managed default so UI is never blank
      if (global.SpeechifyAppState && defaultPath) {
        global.SpeechifyAppState.setModelStorage({
          path: defaultPath,
          rawPath: defaultPath,
          isManaged: true,
          displayTitle: "Veyra managed storage",
          displaySubtext: "Models are stored locally on this computer.",
          modelsCount: 0,
          accessible: true,
          error: null
        });
      }

      // 2. Attempt quick live rescan if engine is online
      try {
        const info = await this.rescan();
        if (info && info.success && info.storagePath) {
          return info.storagePath;
        }
      } catch (err) {
        console.warn("[StorageService] Initial rescan warning:", err);
      }

      return defaultPath;
    }

    /**
     * Interactive folder picker supporting both UXP localFileSystem and CEP ExtendScript.
     * @returns {Promise<{cancelled: boolean, path?: string, error?: string}>}
     */
    async pickFolder() {
      // 1. Try UXP LocalFileSystem Folder Picker
      if (typeof window !== 'undefined' && window.require) {
        try {
          const uxp = window.require('uxp');
          if (uxp && uxp.storage && uxp.storage.localFileSystem) {
            const folder = await uxp.storage.localFileSystem.getFolder();
            if (!folder) {
              return { cancelled: true };
            }
            const nativePath = folder.nativePath || folder.name;
            return { cancelled: false, path: nativePath };
          }
        } catch (uxpErr) {
          console.warn("[StorageService] UXP getFolder error or unsupported:", uxpErr);
        }
      }

      // 2. Try CEP ExtendScript Folder Dialog
      if (typeof window !== 'undefined' && window.CSInterface) {
        try {
          const cs = new window.CSInterface();
          const jsxCode = `(function(){ var f = Folder.selectDialog("Choose Veyra Model Storage Location"); return f ? f.fsName : ""; })()`;
          const selectedPath = await new Promise(resolve => {
            cs.evalScript(jsxCode, res => resolve(res));
          });
          if (selectedPath && selectedPath !== "undefined" && selectedPath !== "null" && selectedPath.trim() !== "") {
            return { cancelled: false, path: selectedPath.trim() };
          } else {
            return { cancelled: true };
          }
        } catch (cepErr) {
          console.warn("[StorageService] CEP folder dialog error:", cepErr);
        }
      }

      return {
        cancelled: false,
        error: "Folder picker not directly available in this host."
      };
    }

    /**
     * Transactionally updates the model storage location.
     * Retains previous valid path if anything fails.
     * @param {string} targetPath
     * @returns {Promise<{success: boolean, storagePath?: string, models?: object, error?: string}>}
     */
    async setLocation(targetPath) {
      const cleanPath = (targetPath || "").trim();
      if (!cleanPath) {
        return { success: false, error: "Please provide a valid directory path." };
      }

      // 1. Filesystem verification if Node.js fs is available
      if (fs) {
        try {
          if (fs.existsSync(cleanPath)) {
            const stat = fs.statSync(cleanPath);
            if (!stat.isDirectory()) {
              return {
                success: false,
                error: "The specified path is a file, not a directory. Please choose a folder."
              };
            }
          }
        } catch (fsErr) {
          return {
            success: false,
            error: `Couldn't access this folder. Choose another location.`
          };
        }
      }

      // 2. Transmit to Engine via explicit configuration endpoint
      let resp = null;
      let data = null;

      try {
        resp = await fetch(`${this.baseUrl}/config/model-storage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: cleanPath })
        });
        data = await resp.json();
      } catch (netErr) {
        return {
          success: false,
          error: "Speech engine is not responding. Please retry once engine is ready."
        };
      }

      if (!resp.ok || !data || !data.success) {
        return {
          success: false,
          error: (data && data.error) ? data.error : "Failed to update model storage location."
        };
      }

      // 3. Update authoritative AppState
      if (global.SpeechifyAppState) {
        global.SpeechifyAppState.setModelStorage({
          path: data.storage_path,
          rawPath: data.storage_path,
          isManaged: data.is_managed !== false,
          displayTitle: data.display_title || (data.is_managed ? "Veyra managed storage" : "Custom location"),
          displaySubtext: data.display_subtext || data.storage_path,
          modelsCount: data.models_count || 0,
          accessible: true,
          error: null
        });
        if (data.models) {
          global.SpeechifyAppState.setModels(data.models);
        }
      }

      return {
        success: true,
        storagePath: data.storage_path,
        isManaged: data.is_managed !== false,
        displayTitle: data.display_title,
        displaySubtext: data.display_subtext,
        modelsCount: data.models_count,
        models: data.models || {}
      };
    }

    /**
     * Resets the model storage location to the default managed directory (%APPDATA%\Speechify\Models).
     */
    async resetToDefault() {
      let resp = null;
      let data = null;

      try {
        resp = await fetch(`${this.baseUrl}/config/model-storage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reset: true })
        });
        data = await resp.json();
      } catch (netErr) {
        return {
          success: false,
          error: "Speech engine is not responding. Please retry once engine is ready."
        };
      }

      if (!resp.ok || !data || !data.success) {
        return {
          success: false,
          error: (data && data.error) ? data.error : "Failed to reset model storage location."
        };
      }

      if (global.SpeechifyAppState) {
        global.SpeechifyAppState.setModelStorage({
          path: data.storage_path,
          rawPath: data.storage_path,
          isManaged: true,
          displayTitle: data.display_title || "Veyra managed storage",
          displaySubtext: data.display_subtext || "Models are stored locally on this computer.",
          modelsCount: data.models_count || 0,
          accessible: true,
          error: null
        });
        if (data.models) {
          global.SpeechifyAppState.setModels(data.models);
        }
      }

      return {
        success: true,
        storagePath: data.storage_path,
        isManaged: true,
        displayTitle: data.display_title,
        displaySubtext: data.display_subtext,
        modelsCount: data.models_count,
        models: data.models || {}
      };
    }

    /**
     * Explicitly migrates models from source to target directory.
     */
    async migrateModels(sourcePath, targetPath) {
      try {
        const resp = await fetch(`${this.baseUrl}/api/models/migrate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_path: sourcePath,
            target_path: targetPath
          })
        });

        const data = await resp.json();
        if (!resp.ok || !data.success) {
          return {
            success: false,
            error: data.error || "Model migration failed."
          };
        }

        if (global.SpeechifyAppState) {
          global.SpeechifyAppState.setModelStorage({
            path: data.storage_path,
            rawPath: data.storage_path,
            isManaged: data.is_managed !== false,
            displayTitle: data.display_title || "Veyra managed storage",
            displaySubtext: data.display_subtext || data.storage_path,
            modelsCount: data.models_count || 0,
            accessible: true,
            error: null
          });
          if (data.models) {
            global.SpeechifyAppState.setModels(data.models);
          }
        }

        return {
          success: true,
          migratedCount: data.migrated_count || 0,
          storagePath: data.storage_path,
          models: data.models || {}
        };
      } catch (err) {
        return {
          success: false,
          error: "Speech engine is not responding. Could not migrate models."
        };
      }
    }

    /**
     * Rescans the active storage directory and syncs AppState.
     */
    async rescan(timeoutMs = 3000) {
      const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

      try {
        const fetchOpts = controller ? { signal: controller.signal } : {};
        const resp = await fetch(`${this.baseUrl}/api/models`, fetchOpts);
        if (timer) clearTimeout(timer);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (global.SpeechifyAppState) {
          global.SpeechifyAppState.setModelStorage({
            path: data.storage_directory || "",
            rawPath: data.storage_directory || "",
            isManaged: data.is_managed !== false,
            displayTitle: data.display_title || "Veyra managed storage",
            displaySubtext: data.display_subtext || "Models are stored locally on this computer.",
            modelsCount: data.models_count || 0,
            accessible: true,
            error: null
          });
          if (data.models) {
            global.SpeechifyAppState.setModels(data.models);
          }
        }

        return {
          success: true,
          models: data.models,
          storagePath: data.storage_directory,
          isManaged: data.is_managed !== false,
          displayTitle: data.display_title,
          displaySubtext: data.display_subtext,
          modelsCount: data.models_count
        };
      } catch (err) {
        return { success: false, error: err.message };
      }
    }
  }

  const instance = new StorageService();
  global.SpeechifyStorageService = instance;
  global.SpeechifyModelStorageManager = instance;

})(typeof window !== 'undefined' ? window : global);
