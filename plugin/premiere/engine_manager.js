/**
 * Speechify — Engine Lifecycle Manager
 * Single authoritative manager for daemon lifecycle, silent process spawning,
 * health checks, startup diagnostics, watchdog heartbeats, and graceful shutdown.
 */

(function (global) {
  'use strict';

  const nodeRequire = (typeof window !== 'undefined' && window.require)
    ? window.require
    : (typeof require !== 'undefined' ? require : null);

  const cp = nodeRequire ? nodeRequire('child_process') : null;
  const fs = nodeRequire ? nodeRequire('fs') : null;
  const path = nodeRequire ? nodeRequire('path') : null;

  const CONFIG = {
    host: "127.0.0.1",
    port: 8765,
    startupTimeoutMs: 15000,
    healthPollIntervalMs: 500,
    heartbeatIntervalMs: 4000, // 4s ping to feed 15s watchdog
    heartbeatTimeoutSec: 15,   // 15s without heartbeat triggers shutdown
    defaultIdleTimeoutSec: 900 // 15 min idle auto-shutdown
  };

  class EngineManager {
    constructor() {
      this.status = "stopped"; // 'stopped' | 'starting' | 'ready' | 'error' | 'restarting'
      this.error = null;
      this.baseUrl = `http://${CONFIG.host}:${CONFIG.port}`;
      this.activeChildProcess = null;
      this.lastHealthCheck = null;
      this.isRestarting = false;
      this.statusListeners = [];
      this.heartbeatTimer = null;
      this.consecutiveHeartbeatFailures = 0;
    }

    addStatusListener(fn) {
      this.statusListeners.push(fn);
    }

    _notifyStatus(status, detail = {}) {
      this.status = status;
      if (global.SpeechifyAppState) {
        global.SpeechifyAppState.setEngine({
          status: status,
          pid: detail.pid || (this.lastHealthCheck ? this.lastHealthCheck.pid : null),
          port: CONFIG.port,
          error: detail.message || (status === 'error' ? 'Engine startup failed' : null),
          lastHealth: this.lastHealthCheck
        });
      }
      this.statusListeners.forEach(fn => {
        try { fn(status, detail); } catch (e) { console.warn("Listener error:", e); }
      });
    }

    _logStartup(msg) {
      const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
      const line = `[${timestamp}] EngineManager: ${msg}\n`;
      console.log(`[EngineManager] ${msg}`);

      try {
        const pathMgr = global.SpeechifyPathManager;
        if (pathMgr && fs) {
          const paths = pathMgr.getPaths();
          if (paths && paths.engineStartupLog) {
            fs.appendFileSync(paths.engineStartupLog, line, 'utf8');
          }
        }
      } catch (err) {
        // Silently continue if log cannot be appended
      }
    }

    /**
     * Resolves the engine paths via PathManager.
     */
    discover() {
      if (!global.SpeechifyPathManager && nodeRequire && path && fs) {
        try {
          const pmPath = path.resolve(__dirname, '..', 'services', 'path_manager.js');
          if (fs.existsSync(pmPath)) {
            nodeRequire(pmPath);
          }
        } catch (e) {}
      }
      if (global.SpeechifyPathManager) {
        return global.SpeechifyPathManager.getPaths();
      }
      return null;
    }

    findEngine() {
      return this.discover();
    }

    async ensureEngineRunning() {
      return await this.start();
    }

    async checkEngine(timeoutMs = 1500) {
      return await this.healthCheck(timeoutMs);
    }

    /**
     * Probes the health endpoint of the engine.
     * @param {number} timeoutMs
     * @returns {Promise<{online: boolean, data?: object, error?: any}>}
     */
    async healthCheck(timeoutMs = 1500) {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const resp = await fetch(`${this.baseUrl}/health`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          signal: controller.signal
        });
        clearTimeout(id);

        if (resp.ok) {
          const data = await resp.json();
          if (data && (data.status === 'ready' || data.status === 'healthy')) {
            this.lastHealthCheck = data;
            return { online: true, data };
          }
        }
        return { online: false };
      } catch (err) {
        clearTimeout(id);
        return { online: false, error: err };
      }
    }

    /**
     * Starts the local engine daemon silently without terminal popup.
     */
    async start() {
      const t0 = Date.now();
      this._logStartup("resolving runtime");
      const paths = this.discover();
      const tDiscovery = Date.now() - t0;

      if (!paths || !paths.engineScript || (fs && !fs.existsSync(paths.engineScript))) {
        const msg = `Engine script not found: ${paths ? paths.engineScript : 'unknown'}`;
        this._logStartup(`launch failed: ${msg}`);
        this._notifyStatus("error", { message: "Speech engine files not found. Check installation." });
        return { success: false, error: msg };
      }

      this._logStartup(`runtime found: ${paths.pythonExe}`);

      // 1. If engine is already online, reuse it immediately
      const initialCheck = await this.healthCheck(1000);
      if (initialCheck.online) {
        this._logStartup(`existing healthy engine detected (PID: ${initialCheck.data.pid || 'unknown'})`);
        this._logStartup("READY");
        this._notifyStatus("ready", initialCheck.data);
        this.startHeartbeat();
        return { success: true, alreadyRunning: true, data: initialCheck.data };
      }

      // 2. Prevent concurrent spawn attempts
      if (this.status === "starting") {
        this._logStartup("already starting, waiting for readiness");
        return await this.waitUntilReady({ t0, tDiscovery, tSpawn: 0 });
      }

      if (!cp || !fs) {
        const msg = "Node.js child_process unavailable in this context.";
        this._logStartup(`launch failed: ${msg}`);
        this._notifyStatus("error", { message: msg });
        return { success: false, error: msg };
      }

      this._notifyStatus("starting", { message: "Starting speech engine…" });

      // Setup log streams
      const outLogPath = paths.engineLog;
      const errLogPath = paths.startupErrLog;

      let outStream = 'ignore';
      let errStream = 'ignore';

      try {
        if (outLogPath) outStream = fs.openSync(outLogPath, 'a');
        if (errLogPath) errStream = fs.openSync(errLogPath, 'a');
      } catch (e) {
        console.warn("[EngineManager] Could not open log streams:", e);
      }

      const startBanner = `\n--- [${new Date().toISOString()}] Speechify Engine Launch ---\nPython: ${paths.pythonExe}\nScript: ${paths.engineScript}\n`;
      try {
        if (typeof outStream === 'number') fs.writeSync(outStream, startBanner);
      } catch (e) {}

      try {
        this._logStartup(`spawning engine: "${paths.pythonExe}" "${paths.engineScript}" ${CONFIG.port}`);

        const tSpawn0 = Date.now();
        const child = cp.spawn(
          paths.pythonExe,
          [
            paths.engineScript,
            String(CONFIG.port),
            String(CONFIG.heartbeatTimeoutSec),
            String(CONFIG.defaultIdleTimeoutSec)
          ],
          {
            cwd: paths.projectRoot || path.dirname(paths.engineScript),
            detached: true,
            windowsHide: true,
            stdio: ['ignore', outStream, errStream],
            env: Object.assign({}, (typeof process !== 'undefined' ? process.env : (nodeRequire ? nodeRequire('process').env : {})), {
              PYTHONPATH: paths.projectRoot,
              PYTHONUNBUFFERED: "1"
            })
          }
        );
        const tSpawn = Date.now() - tSpawn0;

        this._logStartup(`process PID ${child.pid || 'spawned'}`);

        child.on('error', (err) => {
          this._logStartup(`spawn process error: ${err.message}`);
          this._notifyStatus("error", { message: `Engine failed to launch: ${err.message}` });
        });

        child.on('exit', (code, signal) => {
          this._logStartup(`process exited with code ${code}, signal ${signal}`);
          this.stopHeartbeat();
          if (this.status === "ready" && !this.isRestarting) {
            this._handleUnexpectedExit();
          }
        });

        child.unref();
        this.activeChildProcess = child;

        // Wait for readiness
        return await this.waitUntilReady({ t0, tDiscovery, tSpawn });
      } catch (spawnErr) {
        this._logStartup(`launch failed: ${spawnErr.message}`);
        this._notifyStatus("error", { message: spawnErr.message });
        return { success: false, error: spawnErr.message };
      }
    }

    /**
     * Polls the engine health endpoint until ready or timeout expires.
     */
    async waitUntilReady(options = {}) {
      const timeoutMs = options.timeoutMs || CONFIG.startupTimeoutMs;
      const tHealthStart = Date.now();
      this._logStartup(`waiting for health check (timeout: ${timeoutMs / 1000}s)`);

      while (Date.now() - tHealthStart < timeoutMs) {
        const check = await this.healthCheck(800);
        if (check.online) {
          const tReady = Date.now();
          const tHealthCheck = tReady - tHealthStart;
          const tTotal = tReady - (options.t0 || tHealthStart);

          const serverStartupMs = (check.data && check.data.timings && check.data.timings.server_startup_ms)
            ? check.data.timings.server_startup_ms
            : Math.max(1, tHealthCheck - 40);

          const fmtMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`);

          const timingReport = [
            "----------------------------------------",
            "Engine startup metrics",
            "----------------------------------------",
            `Runtime discovery: ${fmtMs(options.tDiscovery || 0)}`,
            `Process spawn:     ${fmtMs(options.tSpawn || 0)}`,
            `Server startup:    ${fmtMs(serverStartupMs)}`,
            `Health check:      ${fmtMs(tHealthCheck)}`,
            `Total:             ${fmtMs(tTotal)}`,
            "----------------------------------------"
          ].join('\n');

          this._logStartup(timingReport);
          this._logStartup(`READY (PID: ${check.data.pid || 'unknown'})`);
          this._notifyStatus("ready", check.data);
          this.startHeartbeat();
          return { success: true, data: check.data, timings: { tDiscovery: options.tDiscovery, tSpawn: options.tSpawn, tHealthCheck, tTotal } };
        }
        await new Promise(r => setTimeout(r, CONFIG.healthPollIntervalMs));
      }

      // Check startup stderr for diagnostics if available
      let stderrSnippet = "";
      try {
        const paths = this.discover();
        if (paths && paths.startupErrLog && fs && fs.existsSync(paths.startupErrLog)) {
          const content = fs.readFileSync(paths.startupErrLog, 'utf8').trim();
          const lines = content.split('\n');
          stderrSnippet = lines.slice(-6).join(' ').replace(/\r/g, '');
        }
      } catch (e) {}

      const errMsg = `Speech engine couldn't start within ${Math.round(timeoutMs / 1000)}s.`;
      this._logStartup(`health check timed out. ${stderrSnippet ? 'stderr: ' + stderrSnippet : ''}`);
      this._notifyStatus("error", { message: errMsg, timeout: true });
      return { success: false, error: errMsg };
    }

    /**
     * Starts continuous 4-second heartbeat pings to feed the 15-second server watchdog.
     */
    startHeartbeat() {
      this.stopHeartbeat();
      this.consecutiveHeartbeatFailures = 0;

      this.heartbeatTimer = setInterval(async () => {
        try {
          const resp = await fetch(`${this.baseUrl}/heartbeat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp: Date.now() })
          });

          if (resp.ok) {
            this.consecutiveHeartbeatFailures = 0;
          } else {
            this.consecutiveHeartbeatFailures++;
          }
        } catch (e) {
          this.consecutiveHeartbeatFailures++;
        }

        // If 4 consecutive heartbeats fail (16s), the engine is offline
        if (this.consecutiveHeartbeatFailures >= 4) {
          this.stopHeartbeat();
          this._handleUnexpectedExit();
        }
      }, CONFIG.heartbeatIntervalMs);
    }

    stopHeartbeat() {
      if (this.heartbeatTimer) {
        clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = null;
      }
    }

    _handleUnexpectedExit() {
      this._logStartup("engine disconnected unexpectedly");
      this._notifyStatus("error", {
        message: "Speech engine disconnected unexpectedly.",
        unexpected: true
      });
    }

    /**
     * Restarts the speech engine cleanly.
     */
    async restart() {
      this.isRestarting = true;
      this._notifyStatus("restarting", { message: "Restarting speech engine…" });
      await this.stop();
      await new Promise(r => setTimeout(r, 600));
      this.isRestarting = false;
      return await this.start();
    }

    async restartEngine() {
      return await this.restart();
    }

    /**
     * Shuts down the engine cleanly.
     */
    async stop() {
      this.stopHeartbeat();

      try {
        await fetch(`${this.baseUrl}/shutdown`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
      } catch (e) {}

      // Allow brief moment for server to run atexit cleanup
      await new Promise(r => setTimeout(r, 400));

      if (this.activeChildProcess) {
        try {
          this.activeChildProcess.kill();
        } catch (e) {}
        this.activeChildProcess = null;
      }

      // Guarantee lock and pid files are cleaned up
      try {
        const paths = this.discover();
        if (paths && paths.logsDir && fs && path) {
          const lockFile = path.join(paths.logsDir, "engine.lock");
          const pidFile = path.join(paths.logsDir, "engine.pid");
          if (fs.existsSync(lockFile)) fs.unlinkSync(lockFile);
          if (fs.existsSync(pidFile)) fs.unlinkSync(pidFile);
        }
      } catch (e) {}

      this._notifyStatus("stopped");
    }

    getStatus() {
      return {
        status: this.status,
        lastHealth: this.lastHealthCheck,
        baseUrl: this.baseUrl
      };
    }
  }

  global.SpeechifyEngineManager = new EngineManager();

})(typeof window !== 'undefined' ? window : global);
