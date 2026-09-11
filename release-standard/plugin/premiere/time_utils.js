/**
 * Speechify — Centralized Time Utilities & Unit Normalizer
 * Provides bulletproof conversion between Premiere Pro ticks, seconds, frames, and timecode.
 * Prevents giant numbers (e.g. 1872468471:06:40:00) by strictly normalizing all inputs.
 */

(function (global) {
  'use strict';

  const TICKS_PER_SECOND = 254016000000;

  /**
   * Safely normalizes any Premiere time input into floating-point seconds.
   * Handles:
   * - Number of seconds (e.g. 26.5)
   * - String of seconds (e.g. "26.5")
   * - String/Number of ticks (e.g. "6732384768000" or values > 10,000,000)
   * - Premiere Time object { seconds: 26.5, ticks: "..." }
   * - Undefined, null, NaN -> returns 0.0
   */
  function normalizeTimeSeconds(val) {
    if (val === null || val === undefined) return 0.0;

    // Premiere Time object check
    if (typeof val === 'object') {
      if (typeof val.seconds === 'number' && !isNaN(val.seconds)) {
        return val.seconds;
      }
      if (typeof val.seconds === 'string') {
        const parsed = parseFloat(val.seconds);
        if (!isNaN(parsed)) return parsed;
      }
      if (val.ticks) {
        const parsedTicks = parseFloat(val.ticks);
        if (!isNaN(parsedTicks) && parsedTicks > 0) {
          return parsedTicks / TICKS_PER_SECOND;
        }
      }
      return 0.0;
    }

    let num = typeof val === 'number' ? val : parseFloat(val);
    if (isNaN(num)) return 0.0;

    // If the number exceeds 10,000,000, it is definitely a Premiere tick count
    // (10,000,000 seconds would be ~115 days of audio)
    if (num > 10000000) {
      return num / TICKS_PER_SECOND;
    }

    return Math.max(0.0, num);
  }

  /**
   * Converts floating-point seconds into Premiere Pro ticks string.
   */
  function secondsToTicks(seconds) {
    const sec = normalizeTimeSeconds(seconds);
    return Math.round(sec * TICKS_PER_SECOND).toString();
  }

  /**
   * Formats a duration in seconds into clean, human-readable audio duration.
   * Never produces timecode or giant un-normalized strings.
   * Examples:
   *   0.42 -> "0.4 s"
   *   12.5 -> "12.5 s"
   *   65.2 -> "1 min 05 s"
   *   3720 -> "1 hr 02 min"
   */
  function formatDuration(seconds) {
    const sec = normalizeTimeSeconds(seconds);
    if (sec <= 0.0) return "0.0 s";

    if (sec < 60) {
      return `${sec.toFixed(1)} s`;
    }

    const totalSeconds = Math.floor(sec);
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    const pad = (n) => String(n).padStart(2, '0');

    if (m >= 60) {
      const h = Math.floor(m / 60);
      const remM = m % 60;
      return `${h} hr ${pad(remM)} min`;
    }

    return `${m} min ${pad(s)} s`;
  }

  /**
   * Formats a sequence timeline position into standard frame-accurate timecode.
   * HH:MM:SS:FF
   */
  function formatTimecode(seconds, fps = 23.976) {
    const sec = normalizeTimeSeconds(seconds);
    const effectiveFps = (fps && fps > 0) ? fps : 23.976;

    const totalFrames = Math.round(sec * effectiveFps);
    const framesPerSec = Math.round(effectiveFps);
    const framesPerMin = framesPerSec * 60;
    const framesPerHour = framesPerMin * 60;

    const h = Math.floor(totalFrames / framesPerHour);
    const remFramesH = totalFrames % framesPerHour;
    const m = Math.floor(remFramesH / framesPerMin);
    const remFramesM = remFramesH % framesPerMin;
    const s = Math.floor(remFramesM / framesPerSec);
    const f = Math.floor(remFramesM % framesPerSec);

    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(h)}:${pad(m)}:${pad(s)}:${pad(f)}`;
  }

  const TimeUtils = {
    TICKS_PER_SECOND,
    normalizeTimeSeconds,
    secondsToTicks,
    formatDuration,
    formatTimecode
  };

  // Export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = TimeUtils;
  }
  global.SpeechifyTimeUtils = TimeUtils;

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
