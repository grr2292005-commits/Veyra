const assert = require('assert');
const { TimelinePlacementService } = require('../plugin/services/placement_service.js');

const service = new TimelinePlacementService();

// Test 1: Single clip placement prefers sourceTrackIndex + 1
const seqInfo1 = {
  audioTrackCount: 4,
  audioTracks: [
    { index: 0, name: "A1", locked: false, clips: [{ startSec: 10, endSec: 40 }] },
    { index: 1, name: "A2", locked: false, clips: [] },
    { index: 2, name: "A3", locked: false, clips: [] },
    { index: 3, name: "A4", locked: false, clips: [] }
  ]
};
const res1 = service.findSafeAudioTrack(seqInfo1, 10, 40, 0);
assert.strictEqual(res1.trackIndex, 1, "Should select A2");
assert.strictEqual(res1.isNewTrack, false);

// Test 2: Occupied A2 advances to A3
const seqInfo2 = {
  audioTrackCount: 4,
  audioTracks: [
    { index: 0, name: "A1", locked: false, clips: [{ startSec: 10, endSec: 40 }] },
    { index: 1, name: "A2", locked: false, clips: [{ startSec: 20, endSec: 30 }] }, // Occupied!
    { index: 2, name: "A3", locked: false, clips: [] },
    { index: 3, name: "A4", locked: false, clips: [] }
  ]
};
const res2 = service.findSafeAudioTrack(seqInfo2, 10, 40, 0);
assert.strictEqual(res2.trackIndex, 2, "Should skip occupied A2 and select A3");

// Test 3: Batch reservations prevent collision
service.clearReservations();
service.reserveDestination(1, 10, 40, "job1");
const res3 = service.findSafeAudioTrack(seqInfo1, 20, 30, 0);
assert.strictEqual(res3.trackIndex, 2, "A2 is reserved, should pick A3");

// Test 4: Locked track is rejected
const seqInfo4 = {
  audioTrackCount: 3,
  audioTracks: [
    { index: 0, name: "A1", locked: false, clips: [{ startSec: 10, endSec: 40 }] },
    { index: 1, name: "A2", locked: true, clips: [] }, // Locked!
    { index: 2, name: "A3", locked: false, clips: [] }
  ]
};
const res4 = service.findSafeAudioTrack(seqInfo4, 10, 40, 0);
assert.strictEqual(res4.trackIndex, 2, "Should skip locked A2 and select A3");

// Test 5: New track allocation when all occupied
const seqInfo5 = {
  audioTrackCount: 3,
  audioTracks: [
    { index: 0, name: "A1", locked: false, clips: [{ startSec: 10, endSec: 40 }] },
    { index: 1, name: "A2", locked: false, clips: [{ startSec: 10, endSec: 40 }] },
    { index: 2, name: "A3", locked: false, clips: [{ startSec: 10, endSec: 40 }] }
  ]
};
const res5 = service.findSafeAudioTrack(seqInfo5, 10, 40, 0);
assert.strictEqual(res5.isNewTrack, true);
assert.strictEqual(res5.trackIndex, 3);
assert.strictEqual(res5.trackName, "A4");

console.log("All TimelinePlacementService Node.js tests passed successfully!");
