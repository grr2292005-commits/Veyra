/**
 * Speechify — Path & Runtime Resolution Service
 * Authoritative single source of truth for runtime paths, scripts, logs, and storage.
 * Deterministic resolution without hardcoded user directories.
 */

(function (global) {
  'use strict';

  const nodeRequire = (typeof window !== 'undefined' && window.require)
    ? window.require
    : (typeof require !== 'undefined' ? require : null);

  const fs = nodeRequire ? nodeRequire('fs') : null;
  const path = nodeRequire ? nodeRequire('path') : null;
  const os = nodeRequire ? nodeRequire('os') : null;

  class PathManager {
    constructor() {
      this._resolved = null;
    }

    /**
     * Resolves all required paths deterministically.
     * Searches config file, packaged runtime, relative development paths, and environment variables.
     */
    resolvePaths() {
      if (this._resolved) return this._resolved;

      let pythonExe = null;
      let engineScript = null;
      let projectRoot = null;
      let logsDir = null;
      let defaultModelStorage = null;

      // 1. Determine base extension directory
      let extensionDir = null;
      if (typeof __dirname !== 'undefined') {
        extensionDir = __dirname;
      } else if (path) {
        extensionDir = path.resolve('.');
      }

      // 2. Inspect engine_config.json in extension directory
      if (fs && path && extensionDir) {
        const configCandidates = [
          path.join(extensionDir, 'engine_config.json'),
          path.join(extensionDir, 'premiere', 'engine_config.json'),
          path.join(extensionDir, '..', 'engine_config.json')
        ];

        for (const cfgPath of configCandidates) {
          try {
            if (fs.existsSync(cfgPath)) {
              const raw = fs.readFileSync(cfgPath, 'utf8').replace(/^\uFEFF/, '').trim();
              const cfg = JSON.parse(raw);
              if (cfg.python_exe && fs.existsSync(cfg.python_exe)) {
                pythonExe = cfg.python_exe;
              }
              if (cfg.engine_script && fs.existsSync(cfg.engine_script)) {
                engineScript = cfg.engine_script;
              }
              if (cfg.project_root && fs.existsSync(cfg.project_root)) {
                projectRoot = cfg.project_root;
              }
              if (pythonExe && engineScript) break;
            }
          } catch (e) {
            console.warn("[PathManager] Config file parse error:", e);
          }
        }
      }

      // 3. Traversal from extension folder for engine script and project root
      if ((!engineScript || !projectRoot) && fs && path && extensionDir) {
        let cursor = extensionDir;
        for (let i = 0; i < 5; i++) {
          const candServer = path.join(cursor, 'engine', 'server.py');
          const candVeyraServer = path.join(cursor, 'Veyra', 'engine', 'server.py');
          const candProServer = path.join(cursor, 'SpeechEnhancerPro', 'engine', 'server.py');
          const candSpeechify = path.join(cursor, 'Speechify', 'engine', 'server.py');

          if (fs.existsSync(candServer)) {
            engineScript = candServer;
            projectRoot = cursor;
            break;
          } else if (fs.existsSync(candVeyraServer)) {
            engineScript = candVeyraServer;
            projectRoot = path.join(cursor, 'Veyra');
            break;
          } else if (fs.existsSync(candSpeechify)) {
            engineScript = candSpeechify;
            projectRoot = path.join(cursor, 'Speechify');
            break;
          } else if (fs.existsSync(candProServer)) {
            engineScript = candProServer;
            projectRoot = path.join(cursor, 'SpeechEnhancerPro');
            break;
          }
          const parent = path.dirname(cursor);
          if (parent === cursor) break;
          cursor = parent;
        }
      }

      // 4. User profile / Desktop candidate fallback
      if ((!engineScript || !projectRoot) && fs && path && os) {
        const homeDir = (typeof process !== 'undefined' && process.env && process.env.USERPROFILE)
          ? process.env.USERPROFILE
          : (os.homedir ? os.homedir() : "");

        if (homeDir) {
          const candidates = [
            path.join(homeDir, 'AppData', 'Local', 'Veyra'),
            path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Veyra'),
            path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Veyra'),
            path.join(homeDir, 'AppData', 'Local', 'Speechify'),
            path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Speechify'),
            path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Speechify')
          ];
          for (const cand of candidates) {
            const candServer = path.join(cand, 'engine', 'server.py');
            if (fs.existsSync(candServer)) {
              engineScript = candServer;
              projectRoot = cand;
              break;
            }
          }
        }
      }

      // 5. Resolve Python executable
      // CRITICAL: Always prioritize pythonw.exe over python.exe on Windows to eliminate console popups
      if (!pythonExe && projectRoot && fs && path) {
        const venvCandidates = [
          path.join(projectRoot, 'runtime', 'Scripts', 'pythonw.exe'),
          path.join(projectRoot, 'runtime', 'Scripts', 'python.exe'),
          path.join(projectRoot, 'runtime', 'bin', 'pythonw.exe'),
          path.join(projectRoot, 'runtime', 'bin', 'python'),
          path.join(projectRoot, 'runtime', 'pythonw.exe'),
          path.join(projectRoot, '.venv', 'Scripts', 'pythonw.exe'),
          path.join(projectRoot, '.venv', 'Scripts', 'python.exe'),
          path.join(projectRoot, '.venv', 'bin', 'python')
        ];

        for (const venvPy of venvCandidates) {
          if (fs.existsSync(venvPy)) {
            pythonExe = venvPy;
            break;
          }
        }
      }

      // Check environment variable
      if (!pythonExe && typeof process !== 'undefined' && process.env && process.env.SPEECHIFY_PYTHON_EXE) {
        if (fs && fs.existsSync(process.env.SPEECHIFY_PYTHON_EXE)) {
          pythonExe = process.env.SPEECHIFY_PYTHON_EXE;
        }
      }

      // Convert python.exe to pythonw.exe on Windows
      if (pythonExe && fs && path && typeof process !== 'undefined' && process.platform === 'win32') {
        if (pythonExe.toLowerCase().endsWith('python.exe')) {
          const wCandidate = path.join(path.dirname(pythonExe), 'pythonw.exe');
          if (fs.existsSync(wCandidate)) {
            pythonExe = wCandidate;
          }
        }
      }

      // Default fallback
      if (!pythonExe) {
        pythonExe = (typeof process !== 'undefined' && process.platform === 'win32') ? "pythonw" : "python";
      }

      // Determine Logs directory
      if (projectRoot && path) {
        logsDir = path.join(projectRoot, 'logs');
        defaultModelStorage = path.join(projectRoot, 'models', 'storage');
      } else if (extensionDir && path) {
        logsDir = path.join(extensionDir, 'logs');
        defaultModelStorage = path.join(extensionDir, 'models', 'storage');
      }

      if (logsDir && fs) {
        try { fs.mkdirSync(logsDir, { recursive: true }); } catch (e) {}
      }

      this._resolved = {
        extensionDir: extensionDir || "",
        pythonExe: pythonExe || "pythonw",
        engineScript: engineScript || "",
        projectRoot: projectRoot || "",
        logsDir: logsDir || "",
        engineStartupLog: logsDir && path ? path.join(logsDir, 'engine-startup.log') : "engine-startup.log",
        engineLog: logsDir && path ? path.join(logsDir, 'engine.log') : "engine.log",
        startupErrLog: logsDir && path ? path.join(logsDir, 'startup.log') : "startup.log",
        defaultModelStorage: defaultModelStorage || ""
      };

      return this._resolved;
    }

    getPaths() {
      return this.resolvePaths();
    }
  }

  global.SpeechifyPathManager = new PathManager();

})(typeof window !== 'undefined' ? window : global);
