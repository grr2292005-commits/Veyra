# Speechify — Timeline Processing & Gap Preservation

## 1. Overview

A critical requirement of professional NLE audio tooling is timeline fidelity. When an editor selects multiple audio clips separated by silence or non-dialogue elements (e.g. `[Clip A] ... 10s gap ... [Clip B]`), Speechify must **never** concatenate them, shift their relative offsets, or overwrite unselected material.

---

## 2. Multi-Clip Architecture

### The Problem with Concatenation
Naive speech tools often export the entire timeline range as one continuous WAV file, or join selected clips into one block. This introduces two severe issues:
1. Gaps between clips are filled with processed background silence or destroyed.
2. Replacing clips on the timeline shifts all downstream edit cuts and breaks audio-video sync.

### Speechify's Discrete Queue Model
Speechify treats each selected timeline clip as an independent, atomic processing job:

1. **Clip Extraction**: Each clip's `mediaPath`, `inPointSec`, `outPointSec`, `startTimeSec`, and `trackIndex` are queried via ExtendScript (`hostscript.jsx`).
2. **Deterministic Naming**: Enhanced files are named based on the clip name:
   $$\text{enhanced\_[CleanClipName]\_00.wav}$$
   Special characters (`\`, `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) are sanitized to comply with Windows filesystem rules.
3. **Sequential Execution**: Clips are processed through the local neural pipeline sequentially to prevent GPU VRAM exhaustion.
4. **Independent Placement**: Upon completion of each clip, `placeEnhancedClip` places the output at the exact original `startTimeSec` on the target audio track.

```text
Original Timeline:
Track A1: [  Clip A  ] ------------ (10s gap) ------------ [  Clip B  ]
           (at 0.0s)                                        (at 15.0s)

Speechify Placement (New Track A2):
Track A2: [Enhanced A] ------------ (10s gap) ------------ [Enhanced B]
           (at 0.0s)                                        (at 15.0s)
```

---

## 3. Tick Normalization & Time Safety

Premiere Pro's ExtendScript API internally measures sequence length and clip points in integer "ticks" ($254,016,000,000\text{ ticks/second}$). If raw ticks are parsed directly without conversion, timecodes expand into astronomical figures (such as `1872468471:06:40:00`).

Speechify's `TimeUtils` (`plugin/premiere/time_utils.js`) normalizes all time values:

```javascript
const TICKS_PER_SECOND = 254016000000;

function normalizeTimeSeconds(val) {
  if (typeof val === 'object' && val !== null) {
    if (val.seconds !== undefined) return Number(val.seconds);
    if (val.ticks !== undefined) return Number(val.ticks) / TICKS_PER_SECOND;
  }
  const n = Number(val);
  // Detect raw ticks (> 10,000,000 corresponds to > 115 days)
  if (n > 10000000) {
    return n / TICKS_PER_SECOND;
  }
  return n;
}
```

---

## 4. Placement Modes

| Mode | Behavior | Use Case |
| :--- | :--- | :--- |
| **New Track** (Default) | Automatically creates a new audio track (e.g. `Speechify Enhanced`) and places clips at their exact original start times. Mutes or leaves original track for easy A/B comparison. | Commercial production, editorial workflows. |
| **Replace** | Swaps the original clip on the existing track with the enhanced WAV file at the exact in/out cut points. | Quick fixes, rough cuts. |
| **Project Bin Only** | Imports enhanced audio into a dedicated `Speechify Enhanced` bin without modifying the timeline. | Manual asset placement. |
