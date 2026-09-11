// Mock a browser environment to test script execution order and errors
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlContent = fs.readFileSync(path.join(__dirname, '..', 'plugin', 'index.html'), 'utf8');

// Minimal mock DOM
const elements = new Map();
function getOrCreateElement(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      innerHTML: '',
      textContent: '',
      style: {},
      classList: {
        add: () => {},
        remove: () => {},
        toggle: () => {},
        contains: () => false
      },
      querySelectorAll: () => [],
      querySelector: () => null,
      appendChild: () => {},
      addEventListener: () => {},
      setAttribute: () => {},
      getAttribute: () => null
    });
  }
  return elements.get(id);
}

// Find all IDs in index.html
const idMatches = [...htmlContent.matchAll(/id=["']([^"']+)["']/g)].map(m => m[1]);
idMatches.forEach(id => getOrCreateElement(id));

const sandbox = {
  window: {
    addEventListener: (event, handler) => {
      if (event === 'DOMContentLoaded') {
        sandbox.domContentLoadedHandler = handler;
      }
    }
  },
  document: {
    getElementById: (id) => getOrCreateElement(id),
    createElement: (tag) => ({
      tagName: tag,
      innerHTML: '',
      textContent: '',
      style: {},
      classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
      dataset: {},
      querySelectorAll: () => [],
      querySelector: () => null,
      appendChild: () => {},
      addEventListener: () => {},
      setAttribute: () => {},
      getAttribute: () => null
    }),
    addEventListener: () => {},
    removeEventListener: () => {},
    activeElement: null,
    readyState: 'complete'
  },
  navigator: { userAgent: 'Node', appVersion: 'Windows' },
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  require: require,
  AbortController: (typeof AbortController !== 'undefined' ? AbortController : class MockAbortController {
    constructor() { this.signal = {}; }
    abort() {}
  }),
  addEventListener: (event, handler) => {
    if (event === 'DOMContentLoaded') {
      sandbox.domContentLoadedHandler = handler;
    }
  },
  removeEventListener: () => {},
  fetch: async () => ({ ok: false, status: 503, json: async () => ({ error: 'Mock' }) })
};
sandbox.window = sandbox;
sandbox.global = sandbox;
sandbox.__SPEECHIFY_TEST_ENV__ = true;
sandbox.window.__SPEECHIFY_TEST_ENV__ = true;

const scripts = [
  'plugin/premiere/CSInterface.js',
  'plugin/premiere/time_utils.js',
  'plugin/state/app_state.js',
  'plugin/services/path_manager.js',
  'plugin/services/storage_service.js',
  'plugin/premiere/dom_bridge.js',
  'plugin/premiere/engine_manager.js',
  'plugin/services/boot_controller.js',
  'plugin/index.js'
];

console.log("Testing script evaluation order...");
for (const script of scripts) {
  try {
    const code = fs.readFileSync(path.join(__dirname, '..', script), 'utf8');
    vm.runInNewContext(code, sandbox, { filename: script });
    console.log(`[OK] Evaluated ${script}`);
  } catch (err) {
    console.error(`[FAIL] Error evaluating ${script}:`, err);
    process.exit(1);
  }
}
console.log("All scripts evaluated without syntax or top-level runtime errors!");

if (sandbox.SpeechifyBootController) {
  const status = sandbox.SpeechifyBootController.getStatus();
  console.log("[OK] BootController verified. Initial status:", JSON.stringify(status));
}

if (sandbox.domContentLoadedHandler) {
  console.log("Testing domContentLoadedHandler invocation...");
  try {
    const p = sandbox.domContentLoadedHandler();
    if (p && p.then) {
      p.then(() => console.log("[OK] Boot promise completed."))
       .catch(err => console.error("[FAIL] Boot promise rejected:", err));
    }
  } catch (initErr) {
    console.error("[FAIL] Handler threw an error:", initErr);
  }
}

