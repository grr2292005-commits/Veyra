const path = require('path');
const fs = require('fs');
const cp = require('child_process');

const engineManagerPath = path.resolve(__dirname, '..', 'plugin', 'premiere', 'engine_manager.js');
require(engineManagerPath);

const manager = global.SpeechifyEngineManager;
const paths = manager.findEngine();

async function testWatchdog() {
  console.log("==================================================");
  console.log("TESTING ENGINE HEARTBEAT WATCHDOG AUTO-SHUTDOWN");
  console.log("==================================================");

  const testPort = 8769;
  const heartbeatTimeout = 3; // 3 seconds timeout
  const idleTimeout = 900;
  const gracePeriod = 2;      // 2 seconds grace period

  console.log(`[Step 1] Spawning engine on port ${testPort} with 3s heartbeat timeout and 2s grace period...`);
  const child = cp.spawn(
    paths.pythonExe,
    [paths.engineScript, String(testPort), String(heartbeatTimeout), String(idleTimeout), String(gracePeriod)],
    {
      cwd: paths.projectRoot,
      detached: true,
      windowsHide: true,
      stdio: 'ignore'
    }
  );
  child.unref();

  const pid = child.pid;
  console.log(`[OK] Spawned process PID: ${pid}`);

  // Wait for it to become ready
  const baseUrl = `http://127.0.0.1:${testPort}`;
  let ready = false;
  const startTime = Date.now();

  while (Date.now() - startTime < 10000) {
    try {
      const resp = await fetch(`${baseUrl}/health`);
      if (resp.ok) {
        ready = true;
        break;
      }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 400));
  }

  if (!ready) {
    console.error("FAIL: Test engine failed to become ready within 10s");
    try { process.kill(pid); } catch (e) {}
    process.exit(1);
  }

  console.log(`[OK] Engine verified ready on port ${testPort} in ${Date.now() - startTime}ms`);

  // Now, DO NOT send any heartbeats!
  // The grace period is 2s, and heartbeat timeout is 3s. Total expected lifetime is ~5-6 seconds.
  console.log(`[Step 2] Observing watchdog: waiting 7 seconds without sending any heartbeats...`);
  await new Promise(r => setTimeout(r, 7000));

  // Check if process has terminated
  console.log(`[Step 3] Probing engine status after watchdog expiry...`);
  let isStillAlive = false;
  try {
    const resp = await fetch(`${baseUrl}/health`);
    if (resp.ok) {
      isStillAlive = true;
    }
  } catch (e) {
    isStillAlive = false;
  }

  if (isStillAlive) {
    console.error("FAIL: Engine was still alive after heartbeat timeout elapsed!");
    try { process.kill(pid); } catch (e) {}
    process.exit(1);
  }

  // Check if PID is gone in OS
  try {
    const isRunningInOS = cp.execSync(
      `powershell -NoProfile -Command "Get-Process -Id ${pid} -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"`,
      { encoding: 'utf8' }
    ).trim();
    if (isRunningInOS !== "0") {
      console.error(`FAIL: Process ${pid} is still running in OS!`);
      try { process.kill(pid); } catch (e) {}
      process.exit(1);
    }
  } catch (err) {}

  console.log(`[OK] Engine cleanly self-terminated automatically when heartbeats stopped.`);
  console.log("==================================================");
  console.log("WATCHDOG AUTO-SHUTDOWN TEST PASSED!");
  console.log("==================================================");
  process.exit(0);
}

testWatchdog().catch(err => {
  console.error("Test error:", err);
  process.exit(1);
});
