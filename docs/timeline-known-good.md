# Speechify Timeline Placement — Known-Good Baseline & Regression Analysis

**Document Date:** 2026-09-11  
**Subsystem:** Timeline Placement & Premiere Pro ProjectItem Import  
**Primary Reference:** `plugin/jsx/hostscript.jsx`, `plugin/premiere/dom_bridge.js`, `plugin/index.js`

---

## 1. Previous Known-Working Placement Implementation

Before recent multi-track and QE DOM modifications, Speechify used a straightforward ExtendScript placement implementation:

```javascript
placeEnhancedClip: function(jsonString) {
    try {
        var options = JSON.parse(jsonString); // Or decoded payload
        var wavPath = options.wavPath;
        var clipName = options.clipName || "Enhanced Audio";
        var startTimeSec = parseFloat(options.startTimeSec) || 0.0;
        var placementMode = options.placementMode || "new_track";

        if (!app.project || !app.project.activeSequence) {
            return JSON.stringify({ success: false, error: "No active sequence" });
        }

        var project = app.project;
        var seq = project.activeSequence;

        // Step 1: Find or create bin 'Speechify'
        var targetBin = null;
        var rootItem = project.rootItem;
        for (var i = 0; i < rootItem.children.numItems; i++) {
            var item = rootItem.children[i];
            if (item.type === 2 && item.name === "Speechify") {
                targetBin = item;
                break;
            }
        }
        if (!targetBin) {
            targetBin = rootItem.createBin("Speechify");
        }

        // Step 2: Import audio file
        var importSuccess = project.importFiles([wavPath], true, targetBin, false);
        if (!importSuccess) {
            return JSON.stringify({ success: false, error: "Failed to import " + wavPath });
        }

        // Find imported project item
        var importedItem = null;
        for (var j = 0; j < targetBin.children.numItems; j++) {
            var child = targetBin.children[j];
            if (child.getMediaPath() === wavPath || child.name.indexOf(clipName) !== -1) {
                importedItem = child;
                break;
            }
        }
        if (!importedItem && targetBin.children.numItems > 0) {
            importedItem = targetBin.children[targetBin.children.numItems - 1];
        }

        if (!importedItem) {
            return JSON.stringify({ success: false, error: "Imported file not found in bin" });
        }

        if (placementMode === 'project_only') {
            return JSON.stringify({ success: true, message: "Imported to Speechify bin" });
        }

        // Step 3: Target Audio Track
        var numTracks = seq.audioTracks.numTracks;
        var targetTrack = null;

        // Find first empty track or use highest track
        for (var t = 0; t < numTracks; t++) {
            if (seq.audioTracks[t].clips.numItems === 0) {
                targetTrack = seq.audioTracks[t];
                break;
            }
        }
        if (!targetTrack && numTracks > 0) {
            targetTrack = seq.audioTracks[numTracks - 1];
        }

        if (!targetTrack) {
            return JSON.stringify({ success: false, error: "No audio track available" });
        }

        // Step 4: Insert Clip at Exact Frame Start Ticks
        var timeTicks = Math.round(startTimeSec * $._voxforge.TICKS_PER_SEC).toString();
        targetTrack.insertClip(importedItem, timeTicks);

        return JSON.stringify({
            success: true,
            placedTrack: targetTrack.name,
            startTimeSec: startTimeSec
        });

    } catch (err) {
        return JSON.stringify({ success: false, error: err.toString() });
    }
}
```

### Key Properties of the Known-Working Baseline:
1. **API Used:** `targetTrack.insertClip(importedItem, timeTicks)` where `importedItem` is a valid `ProjectItem` inside the Speechify bin, and `timeTicks = Math.round(startTimeSec * 254016000000).toString()`.
2. **Bin Isolation:** Files are imported into bin `"Speechify"`.
3. **Clip Identification:** Checks `child.getMediaPath() === wavPath` (and path normalization) and falls back safely to recently imported items in the target bin.
4. **Clean Execution:** No external QE DOM mutations (`qe.project.getActiveSequence().addTracks()`), no unverified track additions, no multi-level complex wrappers.

---

## 2. Relevant Files

* **`plugin/jsx/hostscript.jsx`**: ExtendScript host running inside Premiere Pro. Manages sequence inspection, bin import, `insertClip`, track queries.
* **`plugin/premiere/dom_bridge.js`**: JavaScript bridge between CEP panel and ExtendScript / UXP.
* **`plugin/index.js`**: Orchestrates UI events, background polling, queue creation, and placement triggers.
* **`engine/audio/pipeline.py`**: Handles audio range extraction, timeline clip compositing, WAV writing, and normalization.
* **`engine/server.py`**: Backend endpoints (`/api/audio/prepare-sequence`, `/api/enhance`).

---

## 3. The Regressions Identified

1. **Upward Destination Selection (Choosing tracks ABOVE the source):**
   - Candidate loop wrapped around to `0` through `sourceTrackIndex - 1`.
   - When A2 was enhanced, if A3 had audio, the candidate loop checked A1. Since A1 was empty, it placed the result on A1 (above A2!).
   - Violates the rule: **Never move upward by default**. The visual hierarchy must always be:
     ```text
     Original (A2)
     Enhanced (A3 / A4 / A5)
     ```
2. **Unexpected Empty Track Creation via QE DOM (`addTracks(0)`):**
   - QE DOM `addTracks` signature is `addTracks(numVideoTracks, numAudioTracks)`.
   - Calling `qeSeq.addTracks(0)` passed `numVideoTracks = 0`, with `numAudioTracks` undefined, or created unwanted/corrupted tracks.
   - Creating tracks dynamically without verifying existing lower tracks first caused unexpected empty tracks on the timeline.
3. **Missing Waveform / Silent Output on Full Sequence / In-Out:**
   - In `createFreshTimelineSnapshot`, `seq.end` can be undefined or 0 in ExtendScript unless calculated from timeline clips.
   - When `rangeOut` evaluated to 0 or a short duration, `composite_timeline_audio` skipped timeline clips, generating silence or empty files.
   - Path normalization differences between Windows backslashes (`\`) and forward slashes (`/`) caused `child.getMediaPath() === wavPath` to fail.
   - `clipName` mismatch (`_Full` suffix in `clipName` vs actual filename) prevented finding the newly imported `ProjectItem`, falling back to the wrong bin item.
4. **Overwriting / Replacing Original Source:**
   - In an intermediate patch, `overwriteClip` was called on `options.trackIndex` (the source track), destroying original audio.

---

## 4. Path Forward: Single-Clip Known-Good Baseline First

1. **Restore known-working single clip placement**:
   - Source: A1 (`00:00:10` -> `00:00:40`).
   - Destination: First safe track *below* source (e.g. A2) at `00:00:10`.
   - Original on A1 remains completely untouched.
   - Output WAV validated for non-zero RMS, valid WAV header, correct duration.
   - Verified ProjectItem with valid media path in Speechify bin.
   - Verified TrackItem inserted with non-destructive `insertClip`.
   - Waveform visible and audible.
2. **Then extend to multi-track**:
   - Reuse the exact verified single-clip placement mechanism.
   - Search direction: Strictly `sourceTrackIndex + 1`, `sourceTrackIndex + 2`, ... (downwards only; never upwards to A1).
   - In-memory reservations per batch.
   - Independent jobs per track.
