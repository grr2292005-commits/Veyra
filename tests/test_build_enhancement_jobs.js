const assert = require('assert');
const contextManager = require('../plugin/services/context_manager.js');

console.log("Testing ContextManager.buildEnhancementJobs in Node.js...");

// Test 1: Full Sequence single track with 2 clips and a gap
const snapshot1 = {
  scope: "full_sequence",
  durationSec: 65.0,
  sequenceGuid: "seq_100",
  sequenceName: "Podcast Episode",
  tracks: [
    {
      trackIndex: 0,
      trackName: "A1",
      clips: [
        {
          clipName: "Host_Intro",
          sourcePath: "C:\\Media\\intro.wav",
          timelineStart: 0.0,
          timelineEnd: 25.0,
          durationSec: 25.0,
          inPointSec: 0.0,
          outPointSec: 25.0
        },
        {
          clipName: "Host_Outro",
          sourcePath: "C:\\Media\\outro.wav",
          timelineStart: 40.0,
          timelineEnd: 65.0,
          durationSec: 25.0,
          inPointSec: 5.0,
          outPointSec: 30.0
        }
      ]
    }
  ]
};

const jobs1 = contextManager.buildEnhancementJobs(snapshot1, "batch_test_1");
assert.strictEqual(jobs1.length, 2, "Must produce exactly 2 jobs for 2 clips on A1");
assert.strictEqual(jobs1[0].timelineStart, 0.0);
assert.strictEqual(jobs1[0].timelineEnd, 25.0);
assert.strictEqual(jobs1[0].durationSec, 25.0);
assert.strictEqual(jobs1[0].inPointSec, 0.0);
assert.strictEqual(jobs1[0].outPointSec, 25.0);

assert.strictEqual(jobs1[1].timelineStart, 40.0);
assert.strictEqual(jobs1[1].timelineEnd, 65.0);
assert.strictEqual(jobs1[1].durationSec, 25.0);
assert.strictEqual(jobs1[1].inPointSec, 5.0);
assert.strictEqual(jobs1[1].outPointSec, 30.0);

// Verify total audio duration: 50s, NOT sequence span of 65s!
const totalAudio = jobs1.reduce((sum, j) => sum + j.durationSec, 0);
assert.strictEqual(totalAudio, 50.0, "Total enhanced audio must be 50s, not 65s");

// Test 2: In / Out range intersection with partial slice
const snapshot2 = {
  scope: "in_out",
  inPointSec: 10.0,
  outPointSec: 40.0,
  durationSec: 30.0,
  tracks: [
    {
      trackIndex: 0,
      trackName: "A1",
      clips: [
        {
          clipName: "ClipA",
          sourcePath: "C:\\Media\\clipA.wav",
          timelineStart: 0.0,
          timelineEnd: 20.0,
          durationSec: 20.0,
          inPointSec: 5.0,
          outPointSec: 25.0
        },
        {
          clipName: "ClipB",
          sourcePath: "C:\\Media\\clipB.wav",
          timelineStart: 30.0,
          timelineEnd: 50.0,
          durationSec: 20.0,
          inPointSec: 0.0,
          outPointSec: 20.0
        },
        {
          clipName: "ClipC",
          sourcePath: "C:\\Media\\clipC.wav",
          timelineStart: 60.0,
          timelineEnd: 80.0,
          durationSec: 20.0,
          inPointSec: 0.0,
          outPointSec: 20.0
        }
      ]
    }
  ]
};

const jobs2 = contextManager.buildEnhancementJobs(snapshot2, "batch_test_2");
assert.strictEqual(jobs2.length, 2, "ClipC is outside range; must produce exactly 2 jobs");

// Job A: intersection 10s -> 20s (duration 10s)
assert.strictEqual(jobs2[0].timelineStart, 10.0);
assert.strictEqual(jobs2[0].timelineEnd, 20.0);
assert.strictEqual(jobs2[0].durationSec, 10.0);
assert.strictEqual(jobs2[0].inPointSec, 15.0, "sourceIn offset = 5s + (10s - 0s) = 15s");
assert.strictEqual(jobs2[0].outPointSec, 25.0);

// Job B: intersection 30s -> 40s (duration 10s)
assert.strictEqual(jobs2[1].timelineStart, 30.0);
assert.strictEqual(jobs2[1].timelineEnd, 40.0);
assert.strictEqual(jobs2[1].durationSec, 10.0);
assert.strictEqual(jobs2[1].inPointSec, 0.0, "sourceIn offset = 0s + (30s - 30s) = 0s");
assert.strictEqual(jobs2[1].outPointSec, 10.0);

console.log("All ContextManager.buildEnhancementJobs tests passed successfully!");
