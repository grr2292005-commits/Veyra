const path = require('path');
const fs = require('fs');

global.window = global;
Object.defineProperty(global, 'navigator', {
  value: { appVersion: 'Windows', userAgent: 'Node' },
  configurable: true,
  writable: true
});

// Load modules in order
require(path.resolve(__dirname, '..', 'plugin', 'premiere', 'CSInterface.js'));
require(path.resolve(__dirname, '..', 'plugin', 'premiere', 'time_utils.js'));
require(path.resolve(__dirname, '..', 'plugin', 'state', 'app_state.js'));
require(path.resolve(__dirname, '..', 'plugin', 'services', 'path_manager.js'));
require(path.resolve(__dirname, '..', 'plugin', 'services', 'storage_service.js'));
require(path.resolve(__dirname, '..', 'plugin', 'premiere', 'dom_bridge.js'));
require(path.resolve(__dirname, '..', 'plugin', 'premiere', 'engine_manager.js'));
require(path.resolve(__dirname, '..', 'plugin', 'services', 'boot_controller.js'));

async function testFullBoot() {
  console.log("==================================================");
  console.log("SPEECHIFY FULL BOOT ARCHITECTURE TEST");
  console.log("==================================================");

  const bootCtrl = global.SpeechifyBootController;
  const engineMgr = global.SpeechifyEngineManager;
  const storageSvc = global.SpeechifyStorageService;
  const appState = global.SpeechifyAppState;

  // Clean shutdown any existing engine first
  try {
    await fetch('http://127.0.0.1:8765/shutdown', { method: 'POST' });
    await new Promise(r => setTimeout(r, 600));
  } catch (e) {}

  console.log("[Step 1] Initializing BootController phased boot...");

  let engineReadyFired = false;
  let bootCompletedFired = false;

  bootCtrl.reset();

  const bootResult = await bootCtrl.boot({
    onUIReady: () => {
      console.log("[Boot Hook] onUIReady triggered synchronously.");
    },
    initPremiere: async () => {
      console.log("[Boot Task] Premiere state check running...");
      return { available: false, mock: true };
    },
    initStorage: async () => {
      console.log("[Boot Task] Storage resolution running...");
      const p = await storageSvc.init();
      console.log("[Boot Task] Storage resolved to:", p);
      return p;
    },
    initHardware: async () => {
      console.log("[Boot Task] Hardware baseline initialized.");
      return { baseline: true };
    },
    initEngine: async () => {
      console.log("[Boot Task] Engine starting via EngineManager.start()...");
      const res = await engineMgr.ensureEngineRunning();
      if (!res.success) throw new Error(res.error || "Engine startup failed");
      return res;
    },
    initModels: async () => {
      console.log("[Boot Task] Model discovery & Hardware inspection running...");
      // Check /api/system
      const sysResp = await fetch('http://127.0.0.1:8765/api/system');
      const sysData = await sysResp.json();
      console.log("[Boot Task] Detected hardware:", {
        gpu: sysData.gpu,
        recommendedDevice: sysData.recommendedDevice,
        recommendedModel: sysData.recommended_model
      });

      // Check /api/models
      const modResp = await fetch('http://127.0.0.1:8765/api/models');
      const modData = await modResp.json();
      console.log("[Boot Task] Discovered models count:", Object.keys(modData.models || {}).length);
      return { system: sysData, models: modData };
    },
    onEngineReady: () => {
      console.log("[Boot Hook] onEngineReady triggered!");
      engineReadyFired = true;
    },
    onEngineFailed: (err) => {
      console.error("[Boot Hook] onEngineFailed:", err);
    },
    onBootComplete: (state, services) => {
      console.log("[Boot Hook] onBootComplete triggered with state:", state);
      bootCompletedFired = true;
    }
  });

  console.log("\n==================================================");
  console.log("BOOT SEQUENCE RESULTS");
  console.log("==================================================");
  console.log("Final Boot State:", bootResult.state);
  console.log("Services Status:", JSON.stringify(bootResult.services, null, 2));

  if (bootResult.state !== "READY") {
    console.error("FAIL: Expected final state READY, got:", bootResult.state);
    process.exit(1);
  }
  if (!engineReadyFired) {
    console.error("FAIL: onEngineReady callback was not fired!");
    process.exit(1);
  }
  if (!bootCompletedFired) {
    console.error("FAIL: onBootComplete callback was not fired!");
    process.exit(1);
  }

  // Gracefully stop engine
  console.log("\n[Teardown] Gracefully shutting down engine...");
  await engineMgr.stop();
  console.log("[OK] Engine shut down cleanly.");

  console.log("\n==================================================");
  console.log("SUCCESS: FULL BOOT ARCHITECTURE VALIDATED!");
  console.log("==================================================");
  process.exit(0);
}

testFullBoot().catch(err => {
  console.error("FATAL ERROR in testFullBoot:", err);
  process.exit(1);
});
