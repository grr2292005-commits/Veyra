/**
 * Speechify — Timeline Placement Service
 * Authoritative service for non-destructive audio placement, dynamic safe-track discovery,
 * interval overlap verification, and batch reservation tracking.
 *
 * Invariant: Source audio clips and source tracks are sacred and must NEVER be overwritten,
 * replaced, or deleted.
 */

(function (global) {
  'use strict';

  class TimelinePlacementService {
    constructor() {
      // In-memory reservation map for the active enhancement batch
      // Format: { [trackIndex: number]: Array<{ startSec: number, endSec: number, jobId: string }> }
      this.batchReservations = {};
      this.TICKS_PER_SEC = 254016000000;
    }

    /**
     * Resets all batch reservations. Must be called at the start of every enhancement batch.
     */
    clearReservations() {
      this.batchReservations = {};
    }

    /**
     * Returns current in-memory reservations.
     */
    getReservations() {
      return JSON.parse(JSON.stringify(this.batchReservations));
    }

    /**
     * Checks if a given time interval [startTimeSec, endTimeSec] on a candidate track is completely
     * free of existing timeline clips and pending batch reservations.
     *
     * @param {Object} track - Track object with { id, index, name, locked, clips: [{ startSec, endSec }] }
     * @param {number} startTimeSec - Proposed start time in seconds
     * @param {number} endTimeSec - Proposed end time in seconds
     * @param {Object} [customReservations] - Optional override reservations map
     * @returns {boolean} True if the track is unlocked and has ZERO overlapping audio in the interval
     */
    isIntervalSafe(track, startTimeSec, endTimeSec, customReservations = null) {
      if (!track) return false;

      // Rule 22: Do NOT treat locked track as empty/safe
      if (track.locked === true) {
        return false;
      }

      const tolerance = 0.0001; // Avoid floating point boundary false positives
      const start = Math.max(0, startTimeSec);
      const end = Math.max(start, endTimeSec);

      // 1. Inspect existing Premiere clips on the candidate track
      if (track.clips && Array.isArray(track.clips)) {
        for (let i = 0; i < track.clips.length; i++) {
          const clip = track.clips[i];
          const clipStart = (clip.startSec !== undefined) ? clip.startSec : (clip.inPoint || 0);
          const clipEnd = (clip.endSec !== undefined) ? clip.endSec : (clip.outPoint || clipStart);

          // Interval overlap test: start < clipEnd && end > clipStart
          if (start < clipEnd - tolerance && end > clipStart + tolerance) {
            return false; // Occupied!
          }
        }
      }

      // 2. Inspect active batch reservations on this track index
      const reservations = customReservations || this.batchReservations;
      const trackIndex = track.index !== undefined ? track.index : 0;
      const trackResList = reservations[trackIndex];

      if (trackResList && Array.isArray(trackResList)) {
        for (let j = 0; j < trackResList.length; j++) {
          const res = trackResList[j];
          if (start < res.endSec - tolerance && end > res.startSec + tolerance) {
            return false; // Already reserved by another item in this batch!
          }
        }
      }

      return true;
    }

    /**
     * Finds the lowest-numbered safe audio track for placing enhanced audio.
     *
     * Priority:
     * 1. Start check at preferred track: sourceTrackIndex + 1 (immediately below original)
     * 2. Continue scanning downwards: sourceTrackIndex + 2 ... numTracks - 1
     * 3. Wrap check from track 0 ... sourceTrackIndex - 1 (strictly excluding sourceTrackIndex!)
     * 4. If all existing tracks are occupied/locked, allocate next new track (index = numTracks)
     *
     * @param {Object} sequenceInfo - { audioTracks: [...], audioTrackCount: number }
     * @param {number} startTimeSec - Start time in seconds
     * @param {number} endTimeSec - End time in seconds
     * @param {number|null} sourceTrackIndex - Index of originating source track (strictly forbidden from reuse)
     * @param {Object} [customReservations] - Optional reservations map
     * @returns {Object} { success: boolean, trackIndex: number, isNewTrack: boolean, trackName: string, error?: string }
     */
    findSafeAudioTrack(sequenceInfo, startTimeSec, endTimeSec, sourceTrackIndex = null, customReservations = null) {
      if (!sequenceInfo) {
        return { success: false, trackIndex: -1, error: "No active sequence info provided" };
      }

      const tracks = sequenceInfo.audioTracks || [];
      const numTracks = sequenceInfo.audioTrackCount !== undefined ? sequenceInfo.audioTrackCount : tracks.length;

      // Construct ordered list of candidate track indices
      const candidateIndices = [];

      if (sourceTrackIndex !== null && sourceTrackIndex !== undefined && !isNaN(sourceTrackIndex)) {
        const srcIdx = parseInt(sourceTrackIndex, 10);

        // Strict Requirement: Destination search starts strictly BELOW the source track
        // Priority: sourceTrackIndex + 1, sourceTrackIndex + 2 ... numTracks - 1
        // NEVER search tracks above the source (e.g. A1 when source is on A2)
        for (let t = srcIdx + 1; t < numTracks; t++) {
          candidateIndices.push(t);
        }
      } else {
        // No source track specified: scan 0 ... numTracks - 1
        for (let t = 0; t < numTracks; t++) {
          candidateIndices.push(t);
        }
      }

      const candidateLogs = [];

      // Check each candidate track for occupancy & lock state
      for (let c = 0; c < candidateIndices.length; c++) {
        const candIdx = candidateIndices[c];
        const track = tracks[candIdx] || { index: candIdx, name: `A${candIdx + 1}`, locked: false, clips: [] };
        const isSafe = this.isIntervalSafe(track, startTimeSec, endTimeSec, customReservations);
        candidateLogs.push(`track ${candIdx} / ${track.name || ('A' + (candIdx + 1))} / ${isSafe ? 'free' : 'occupied'}`);

        if (isSafe) {
          try {
            console.log(`[Speechify Destination Selection]\nSOURCE: ${sourceTrackIndex !== null ? 'track index ' + sourceTrackIndex : 'none'}\nDESTINATION CANDIDATES:\n${candidateLogs.join('\n')}\nSELECTED: ${track.name || ('A' + (candIdx + 1))} / index ${candIdx}`);
          } catch (e) {}
          return {
            success: true,
            trackIndex: candIdx,
            isNewTrack: false,
            trackName: track.name || `A${candIdx + 1}`,
            candidateLogs: candidateLogs
          };
        }
      }

      // If all existing tracks are occupied or locked, create / use the next audio track
      const newTrackIndex = numTracks;
      try {
        console.log(`[Speechify Destination Selection]\nSOURCE: ${sourceTrackIndex !== null ? 'track index ' + sourceTrackIndex : 'none'}\nDESTINATION CANDIDATES:\n${candidateLogs.join('\n')}\nSELECTED: NEW TRACK A${newTrackIndex + 1} / index ${newTrackIndex}`);
      } catch (e) {}
      return {
        success: true,
        trackIndex: newTrackIndex,
        isNewTrack: true,
        trackName: `A${newTrackIndex + 1}`,
        candidateLogs: candidateLogs
      };
    }

    /**
     * Reserves a destination interval on a track for the active enhancement batch.
     * Prevents subsequent clips/tracks in the same batch from colliding on the same track.
     *
     * @param {number} trackIndex - Destination track index
     * @param {number} startTimeSec - Start time in seconds
     * @param {number} endTimeSec - End time in seconds
     * @param {string} jobId - Unique job ID for tracing
     */
    reserveDestination(trackIndex, startTimeSec, endTimeSec, jobId = "") {
      const idx = parseInt(trackIndex, 10);
      if (isNaN(idx) || idx < 0) return;

      if (!this.batchReservations[idx]) {
        this.batchReservations[idx] = [];
      }

      this.batchReservations[idx].push({
        startSec: Math.max(0, startTimeSec),
        endSec: Math.max(startTimeSec, endTimeSec),
        jobId: jobId || `job_${Date.now()}`
      });
    }

    /**
     * Validates post-insertion TrackItem against expected target parameters.
     *
     * @param {Object} placedResult - Result from hostscript/DOM bridge
     * @param {Object} expected - { sourceTrackIndex, startTimeSec, durationSec, projectItemId }
     * @returns {Object} { valid: boolean, errors: string[] }
     */
    validatePlacement(placedResult, expected = {}) {
      const errors = [];

      if (!placedResult || !placedResult.success) {
        errors.push(placedResult ? (placedResult.error || "Placement failed") : "Null placement result");
        return { valid: false, errors };
      }

      // Rule 1 & 7: Original track must not be reused
      if (expected.sourceTrackIndex !== undefined && expected.sourceTrackIndex !== null) {
        if (placedResult.trackIndex === expected.sourceTrackIndex) {
          errors.push(`Critical violation: Enhanced audio was placed on source track A${expected.sourceTrackIndex + 1}`);
        }
      }

      // Rule 13: Exact timeline start time (tolerance ±0.05s / 1 frame)
      if (expected.startTimeSec !== undefined && expected.startTimeSec !== null) {
        const diff = Math.abs(placedResult.startTimeSec - expected.startTimeSec);
        if (diff > 0.05) {
          errors.push(`Start time mismatch: expected ${expected.startTimeSec}s, got ${placedResult.startTimeSec}s (diff ${diff.toFixed(3)}s)`);
        }
      }

      // Rule 14: Exact duration (tolerance ±0.1s)
      if (expected.durationSec !== undefined && expected.durationSec !== null && placedResult.durationSec !== undefined) {
        const durDiff = Math.abs(placedResult.durationSec - expected.durationSec);
        if (durDiff > 0.1) {
          errors.push(`Duration mismatch: expected ${expected.durationSec}s, got ${placedResult.durationSec}s`);
        }
      }

      return {
        valid: errors.length === 0,
        errors
      };
    }
  }

  // Export as singleton and class
  const instance = new TimelinePlacementService();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TimelinePlacementService, placementService: instance };
  }
  if (typeof global !== 'undefined') {
    global.SpeechifyPlacementService = instance;
    global.TimelinePlacementService = TimelinePlacementService;
  }
})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
