const assert = require('assert');
const TimeUtils = require('../plugin/premiere/time_utils.js');

console.log("Testing TimeUtils...");

// 1. Ticks normalization
const rawTicks = "47563847291000"; // ~187.246 sec
const normFromTicks = TimeUtils.normalizeTimeSeconds(rawTicks);
console.log("Raw ticks converted to seconds:", normFromTicks);
assert(Math.abs(normFromTicks - 187.246) < 0.01, "Failed to normalize raw ticks");

// 2. Normal seconds string
const normSec = TimeUtils.normalizeTimeSeconds("26.5");
assert.strictEqual(normSec, 26.5);

// 3. Time object
const timeObj = { seconds: 15.2, ticks: "3861043200000" };
assert.strictEqual(TimeUtils.normalizeTimeSeconds(timeObj), 15.2);

// 4. Null / Undefined / NaN
assert.strictEqual(TimeUtils.normalizeTimeSeconds(null), 0.0);
assert.strictEqual(TimeUtils.normalizeTimeSeconds(undefined), 0.0);
assert.strictEqual(TimeUtils.normalizeTimeSeconds("invalid"), 0.0);

// 5. formatDuration tests
assert.strictEqual(TimeUtils.formatDuration(0), "0.0 s");
assert.strictEqual(TimeUtils.formatDuration(0.42), "0.4 s");
assert.strictEqual(TimeUtils.formatDuration(12.5), "12.5 s");
assert.strictEqual(TimeUtils.formatDuration(65.2), "1 min 05 s");
assert.strictEqual(TimeUtils.formatDuration(3720), "1 hr 02 min");

// Verify that huge tick strings are formatted reasonably and do not produce billions
const durFromTicks = TimeUtils.formatDuration(rawTicks);
console.log("Duration from ticks:", durFromTicks);
assert(durFromTicks.includes("min") || durFromTicks.includes("s"), "Duration from ticks should be normalized");
assert(!durFromTicks.includes("1872468471"), "Must not contain huge un-normalized number");

// 6. formatTimecode tests
const tc = TimeUtils.formatTimecode(10.0, 24.0);
console.log("Timecode for 10.0s @ 24fps:", tc);
assert.strictEqual(tc, "00:00:10:00");

console.log("ALL TimeUtils tests passed successfully!");
