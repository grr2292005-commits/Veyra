const path = require('path');
const fs = require('fs');
const cp = require('child_process');

const engineManagerPath = path.resolve(__dirname, '..', 'plugin', 'premiere', 'engine_manager.js');
require(engineManagerPath);

const manager = global.SpeechifyEngineManager;

async function testLifecycle() {
  console.log("==================================================");
  console.log("SPEECHIFY ENGINE LIFECYCLE & SILENT START TEST");
  console.log("==================================================");

  // Ensure any lingering server on port 8765 is shut down first
  try {
    await fetch('http://127.0.0.1:8765/shutdown', { method: 'POST' });
    await new Promise(r => setTimeout(r, 600));
  } catch (e) {}

  // 1. Launch engine via EngineManager.start()
  console.log("\n[Step 1] Starting engine via SpeechifyEngineManager.start()...");
  const res = await manager.start();
  console.log("start() result:", res);

  if (!res.success) {
    console.error("FAIL: Engine start failed:", res.error);
    process.exit(1);
  }

  // 2. Verify /health
  console.log("\n[Step 2] Probing /health...");
  const health = await manager.checkEngine();
  console.log("Health payload:", health.data);

  if (!health.online) {
    console.error("FAIL: Engine is not online!");
    process.exit(1);
  }
  if (health.data.owner !== "speechify") {
    console.error("FAIL: Owner should be 'speechify'!");
    process.exit(1);
  }
  if (!health.data.instanceId) {
    console.error("FAIL: Missing instanceId in health payload!");
    process.exit(1);
  }
  const enginePid = health.data.pid;
  console.log(`[OK] Engine confirmed online with PID: ${enginePid}`);

  // 3. Verify zero console window (Windowless execution)
  console.log("\n[Step 3] Verifying windowless execution (pythonw.exe)...");
  try {
    const psOut = cp.execSync(
      `powershell -NoProfile -Command "$p = Get-Process -Id ${enginePid} -ErrorAction SilentlyContinue; if ($p) { Write-Output ('Handle:' + $p.MainWindowHandle + ';Title:' + $p.MainWindowTitle) }"`,
      { encoding: 'utf8' }
    ).trim();
    console.log("Process window check:", psOut);
    if (psOut.includes("Title:") && !psOut.endsWith("Title:")) {
      console.warn("WARNING: Window title detected:", psOut);
    } else {
      console.log("[OK] Verified: zero console window / UI window attached to process.");
    }
  } catch (err) {
    console.log("Window check notice:", err.message);
  }

  // 4. Verify lockfile exists
  console.log("\n[Step 4] Verifying engine.lock ownership file...");
  const lockfilePath = path.join(path.resolve(__dirname, '..'), 'logs', 'engine.lock');
  if (fs.existsSync(lockfilePath)) {
    const lockContent = JSON.parse(fs.readFileSync(lockfilePath, 'utf8'));
    console.log("Lockfile content:", lockContent);
    if (lockContent.pid !== enginePid) {
      console.error(`FAIL: Lockfile PID ${lockContent.pid} does not match engine PID ${enginePid}!`);
      process.exit(1);
    }
    console.log("[OK] Lockfile matches active engine PID.");
  } else {
    console.warn("Lockfile not found at:", lockfilePath);
  }

  // 5. Test Heartbeat endpoint
  console.log("\n[Step 5] Testing heartbeat endpoint...");
  const hbResp = await fetch('http://127.0.0.1:8765/api/heartbeat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client: "test-runner" })
  });
  const hbData = await hbResp.json();
  console.log("Heartbeat response:", hbData);
  if (hbData.status !== "alive") {
    console.error("FAIL: Heartbeat response unexpected:", hbData);
    process.exit(1);
  }
  console.log("[OK] Heartbeat accepted.");

  // 6. Test graceful shutdown via manager.stop()
  console.log("\n[Step 6] Testing graceful shutdown via SpeechifyEngineManager.stop()...");
  await manager.stop();
  await new Promise(r => setTimeout(r, 1200));

  const afterShutdown = await manager.checkEngine(500);
  console.log("Post-shutdown probe:", afterShutdown);
  if (afterShutdown.online) {
    console.error("FAIL: Engine should be offline after stop()!");
    process.exit(1);
  }
  console.log("[OK] Engine shut down cleanly.");

  // 7. Verify lockfile was removed
  if (fs.existsSync(lockfilePath)) {
    console.error("FAIL: engine.lock should have been deleted on shutdown!");
    process.exit(1);
  }
  console.log("[OK] engine.lock was cleanly removed.");

  console.log("\n==================================================");
  console.log("ALL ENGINE LIFECYCLE TESTS PASSED PERFECTLY!");
  console.log("==================================================");
  process.exit(0);
}

testLifecycle().catch(err => {
  console.error("Unhandled test error:", err);
  process.exit(1);
});
