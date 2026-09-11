const path = require('path');
const fs = require('fs');

// Load engine_manager.js
const engineManagerPath = path.resolve(__dirname, '..', 'plugin', 'premiere', 'engine_manager.js');
require(engineManagerPath);

const manager = global.SpeechifyEngineManager;
console.log("EngineManager loaded:", !!manager);

const paths = manager.findEngine();
console.log("Resolved Paths:");
console.log(" - Python Exe:   ", paths.pythonExe, "(exists:", fs.existsSync(paths.pythonExe), ")");
console.log(" - Engine Script:", paths.engineScript, "(exists:", fs.existsSync(paths.engineScript), ")");
console.log(" - Project Root: ", paths.projectRoot, "(exists:", fs.existsSync(paths.projectRoot), ")");

if (!fs.existsSync(paths.pythonExe)) {
  console.error("FAIL: Python executable does not exist!");
  process.exit(1);
}

if (!fs.existsSync(paths.engineScript)) {
  console.error("FAIL: Engine script does not exist!");
  process.exit(1);
}

console.log("SUCCESS: EngineManager successfully resolved verified paths.");
process.exit(0);
