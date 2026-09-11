/**
 * Speechify — Authoritative Boot Controller
 * Orchestrates phased, non-blocking asynchronous application startup.
 * Guarantees that the UI renders first and that no subsystem failure or timeout can crash the panel.
 */

(function (global) {
  'use strict';

  const nodeRequire = (typeof window !== 'undefined' && window.require)
    ? window.require
    : (typeof require !== 'undefined' ? require : null);

  const fs = nodeRequire ? nodeRequire('fs') : null;
  const path = nodeRequire ? nodeRequire('path') : null;

  const BOOT_STATES = {
    BOOTING: "BOOTING",
    UI_READY: "UI_READY",
    SERVICES_STARTING: "SERVICES_STARTING",
    ENGINE_READY: "ENGINE_READY",
    READY: "READY",
    PARTIAL_ERROR: "PARTIAL_ERROR"
  };

  class BootController {
    constructor() {
      this.state = BOOT_STATES.BOOTING;
      this._bootPromise = null;
      this.services = {
        ui: { status: "pending", error: null },
        premiere: { status: "pending", error: null },
        storage: { status: "pending", error: null },
        hardware: { status: "pending", error: null },
        engine: { status: "pending", error: null },
        models: { status: "pending", error: null }
      };
      this.debugMode = false;
      this._logFile = null;
    }

    _resolveLogPath() {
      if (this._logFile) return this._logFile;
      try {
        if (global.SpeechifyPathManager) {
          const paths = global.SpeechifyPathManager.getPaths();
          if (paths && paths.logsDir && path) {
            this._logFile = path.join(paths.logsDir, 'boot.log');
            return this._logFile;
          }
        }
        if (typeof __dirname !== 'undefined' && path) {
          this._logFile = path.join(__dirname, '..', 'logs', 'boot.log');
          return this._logFile;
        }
      } catch (e) {}
      return null;
    }

    log(stage, message = "") {
      const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
      const logLine = `[${ts}] [${stage}] ${message}`.trim();
      console.log(`[BootController] ${logLine}`);

      const targetPath = this._resolveLogPath();
      if (targetPath && fs) {
        try {
          const dir = path.dirname(targetPath);
          if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
          fs.appendFileSync(targetPath, logLine + '\n', 'utf8');
        } catch (e) {
          console.warn("[BootController] Failed to write boot.log:", e);
        }
      }
    }

    /**
     * Executes an isolated service initializer with hard timeout protection.
     * Guaranteed to never throw or allow unhandled promise rejections.
     */
    async runService(name, initFn, timeoutMs = 8000) {
      this.log("START", name);
      this.services[name.toLowerCase()] = { status: "starting", error: null };

      const timeoutPromise = new Promise((_, reject) => {
        const timer = setTimeout(() => {
          clearTimeout(timer);
          reject(new Error(`Service '${name}' initialization timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      });

      try {
        const result = await Promise.race([
          Promise.resolve().then(() => initFn()),
          timeoutPromise
        ]);

        this.services[name.toLowerCase()] = { status: "ready", error: null };
        this.log("OK", name);
        return { success: true, result };
      } catch (err) {
        const errMsg = err ? (err.message || String(err)) : "Unknown initialization error";
        this.services[name.toLowerCase()] = { status: "error", error: errMsg };
        this.log("FAIL", `${name} — ${errMsg}`);
        return { success: false, error: errMsg };
      }
    }

    /**
     * Main application boot entrypoint with singleton guard.
     * The UI must already be mounted and painted before services begin.
     */
    boot(callbacks = {}) {
      if (this._bootPromise) {
        this.log("INFO", "Boot already initialized or in progress. Returning existing bootPromise.");
        return this._bootPromise;
      }

      this._bootPromise = (async () => {
        this.log("START", "Speechify Application Boot Sequence");

        // 1. Mark UI as ready
        this.state = BOOT_STATES.UI_READY;
        this.services.ui = { status: "ready", error: null };
        this.log("OK", "UI Paint & Static Markup");

        if (callbacks.onUIReady) {
          try { callbacks.onUIReady(); } catch (e) { this.log("WARN", `onUIReady callback: ${e.message}`); }
        }

        // 2. Yield control to browser layout/render engine to complete initial paint
        await new Promise(resolve => setTimeout(resolve, 30));

        // 3. Begin independent service initializations in parallel
        this.state = BOOT_STATES.SERVICES_STARTING;
        this.log("START", "Async Subsystem Initialization");

        const tasks = [];

        // Task A: Premiere State Sync (Timeout: 4s)
        if (callbacks.initPremiere) {
          tasks.push(
            this.runService("Premiere", callbacks.initPremiere, 4000)
              .catch(() => {})
          );
        }

        // Task B: Model Storage Resolution (Timeout: 5s)
        if (callbacks.initStorage) {
          tasks.push(
            this.runService("Storage", callbacks.initStorage, 5000)
              .catch(() => {})
          );
        }

        // Task C: Hardware Capability Detection (Timeout: 5s)
        if (callbacks.initHardware) {
          tasks.push(
            this.runService("Hardware", callbacks.initHardware, 5000)
              .catch(() => {})
          );
        }

        // Task D: Engine Lifecycle & Daemon Boot (Timeout: 16s)
        if (callbacks.initEngine) {
          tasks.push(
            this.runService("Engine", callbacks.initEngine, 16000)
              .then(async (res) => {
                if (res && res.success) {
                  this.state = BOOT_STATES.ENGINE_READY;
                  if (callbacks.initModels) {
                    await this.runService("Models", callbacks.initModels, 4000).catch(() => {});
                  }
                  if (callbacks.onEngineReady) callbacks.onEngineReady();
                } else {
                  if (callbacks.onEngineFailed) callbacks.onEngineFailed(res ? res.error : "Engine start failed");
                }
              })
              .catch(() => {})
          );
        }

        // Wait for all initializations to settle without letting any single failure reject the promise
        await Promise.allSettled(tasks);

        // 4. Determine final application readiness
        const hasCriticalFailures = (this.services.engine.status === "error");
        this.state = hasCriticalFailures ? BOOT_STATES.PARTIAL_ERROR : BOOT_STATES.READY;
        this.log(this.state === BOOT_STATES.READY ? "DONE" : "WARN", `Speechify Boot Complete [State: ${this.state}]`);

        if (callbacks.onBootComplete) {
          try { callbacks.onBootComplete(this.state, this.services); } catch (e) {}
        }

        return {
          state: this.state,
          services: this.services
        };
      })();

      return this._bootPromise;
    }

    getStatus() {
      return {
        state: this.state,
        services: Object.assign({}, this.services)
      };
    }

    reset() {
      this._bootPromise = null;
    }
  }

  const instance = new BootController();
  global.SpeechifyBootController = instance;

})(typeof window !== 'undefined' ? window : global);
