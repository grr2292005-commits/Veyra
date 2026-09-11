/**
 * Speechify — Context Manager & Serialization Boundary Service
 * Authoritative specification and validator for PremiereContextSnapshot.
 * Enforces single serialization boundary, pure primitive data payloads, and diagnostic logging.
 */

(function (global) {
  'use strict';

  const nodeRequire = (typeof window !== 'undefined' && window.require)
    ? window.require
    : (typeof require !== 'undefined' ? require : null);

  const fs = nodeRequire ? nodeRequire('fs') : null;
  const path = nodeRequire ? nodeRequire('path') : null;

  class ContextManager {
    constructor() {
      this.SCHEMA_VERSION = 1;
      this.ALLOWED_SCOPES = ['selected_clips', 'in_out', 'full_sequence'];
    }

    /**
     * Single safe deserialization boundary for context payloads.
     * Guaranteed never to call JSON.parse on already-parsed objects.
     * Safely decodes URL-encoded strings, JSON strings, and double-serialized strings.
     */
    parseContext(input) {
      if (input === null || input === undefined) {
        throw new Error("Context payload is null or undefined");
      }

      if (typeof input === 'object') {
        return input;
      }

      if (typeof input === 'string') {
        const trimmed = input.trim();
        if (trimmed.length === 0) {
          throw new Error("Context payload is empty string");
        }

        let str = trimmed;

        // URL-encoded detection (used to safely pass Windows backslashes across evalScript)
        if (str.indexOf('%') !== -1 && (str.startsWith('%7B') || str.startsWith('%5B') || str.indexOf('%22') !== -1)) {
          try {
            str = decodeURIComponent(str);
          } catch (decErr) {
            // Ignore decode failure and attempt raw parse
          }
        }

        let parsed;
        try {
          parsed = JSON.parse(str);
        } catch (jsonErr) {
          throw new Error("JSON.parse failure: " + jsonErr.message);
        }

        // Handle double-serialized JSON strings
        if (typeof parsed === 'string') {
          try {
            const doubleParsed = JSON.parse(parsed);
            if (doubleParsed && typeof doubleParsed === 'object') {
              parsed = doubleParsed;
            }
          } catch (dErr) {
            // Keep first parsed result
          }
        }

        if (!parsed || typeof parsed !== 'object') {
          throw new Error("Context payload did not deserialize to an object");
        }

        return parsed;
      }

      throw new Error(`Unsupported context payload type: ${typeof input}`);
    }

    /**
     * Validates that a snapshot conforms strictly to the PremiereContextSnapshot schema.
     * Returns structured { valid: boolean, errors: [{ code, message }], warnings: [] }.
     * Never throws exceptions to the caller.
     */
    validateStructure(rawSnapshot) {
      const errors = [];
      const warnings = [];

      let snapshot;
      try {
        snapshot = this.parseContext(rawSnapshot);
      } catch (err) {
        return {
          valid: false,
          errors: [{ code: "INVALID_PAYLOAD", message: err.message }],
          warnings: []
        };
      }

      if (!snapshot || typeof snapshot !== 'object') {
        return {
          valid: false,
          errors: [{ code: "NOT_AN_OBJECT", message: "Snapshot must be a non-null object." }],
          warnings: []
        };
      }

      // Check sequence identity
      const seq = snapshot.sequence || {};
      const seqGuid = seq.guid || snapshot.sequenceGuid;
      const seqName = seq.name || snapshot.sequenceName;

      if (!seqGuid && !seqName) {
        errors.push({ code: "MISSING_SEQUENCE_IDENTITY", message: "Snapshot lacks valid sequence identity." });
      }

      // Check scope
      const scope = snapshot.scope;
      if (!scope || !this.ALLOWED_SCOPES.includes(scope)) {
        errors.push({
          code: "INVALID_SCOPE",
          message: `Scope '${scope}' is invalid. Allowed scopes: ${this.ALLOWED_SCOPES.join(', ')}`
        });
      }

      // Check clips array
      const clips = snapshot.clips;
      if (!Array.isArray(clips)) {
        errors.push({ code: "INVALID_CLIPS_TYPE", message: "Snapshot 'clips' must be an array." });
      } else {
        if (scope === 'selected_clips' && clips.length === 0) {
          errors.push({ code: "NO_CLIPS_SELECTED", message: "Select an audio clip in the timeline." });
        }

        for (let i = 0; i < clips.length; i++) {
          const clip = clips[i];
          if (!clip || typeof clip !== 'object') {
            errors.push({ code: "INVALID_CLIP_ITEM", message: `Clip at index ${i} is not a valid object.` });
            continue;
          }

          const path = clip.sourcePath || clip.mediaPath;
          if (!path || typeof path !== 'string' || path.trim().length === 0) {
            errors.push({ code: "MISSING_SOURCE_PATH", message: `Clip '${clip.clipName || clip.name || i}' is missing a valid source media path.` });
          }

          if (typeof clip.trackIndex !== 'number' || clip.trackIndex < 0) {
            errors.push({ code: "INVALID_TRACK_INDEX", message: `Clip '${clip.clipName || clip.name || i}' has invalid trackIndex.` });
          }
        }
      }

      return {
        valid: errors.length === 0,
        errors: errors,
        warnings: warnings,
        sanitizedSnapshot: errors.length === 0 ? snapshot : null
      };
    }

    /**
     * Converts a valid snapshot and clip index into an immutable, pure-primitive EnhancementJob payload.
     * Guarantees zero host objects (no TrackItem, Sequence, ProjectItem, DOMElement, etc.).
     */
    toSafeJobPayload(snapshot, clipIndex, masterJobId) {
      if (!snapshot || !snapshot.clips || !snapshot.clips[clipIndex]) {
        throw new Error(`Clip index ${clipIndex} not found in snapshot.`);
      }

      const clip = snapshot.clips[clipIndex];
      const clipJobId = `${masterJobId}_c${clipIndex}`;
      const seq = snapshot.sequence || {};
      const seqGuid = seq.guid || snapshot.sequenceGuid || "unknown_seq";
      const seqName = seq.name || snapshot.sequenceName || "Sequence";
      const sourcePath = clip.sourcePath || clip.mediaPath;

      const startTime = (typeof clip.timelineStart === 'number') ? clip.timelineStart : (clip.startTimeSec || 0.0);
      const duration = (typeof clip.duration === 'number') ? clip.duration : (clip.durationSec || 1.0);

      // Only primitive types permitted
      return {
        clipJobId: String(clipJobId),
        masterJobId: String(masterJobId),
        sourceFile: String(sourcePath),
        inPointSec: Number(clip.inPointSec || 0.0),
        outPointSec: Number(clip.outPointSec || duration),
        clipName: String(clip.clipName || clip.name || "Enhanced Audio"),
        targetStartTime: Number(startTime),
        targetEndTime: Number(startTime + duration),
        durationSec: Number(duration),
        trackIndex: Number(clip.trackIndex || 0),
        trackName: String(clip.trackName || "A1"),
        projectItemId: String(clip.projectItemId || ""),
        sequenceGuid: String(seqGuid),
        sequenceName: String(seqName),
        fileSize: Number(clip.fileSize || 0),
        fileMtime: Number(clip.fileMtime || 0)
      };
    }

    /**
     * Builds individual EnhancementJob objects for actual audio clips / intersections.
     * Enforces the fundamental invariant: A timeline track is not an audio file;
     * timeline gaps are never rendered as silence.
     * - selected_clips: 1 job per selected clip.
     * - in_out: 1 job per clip intersecting [inPointSec, outPointSec], sliced to intersection.
     * - full_sequence: 1 job per actual clip on selected tracks across the sequence.
     * Every job has direct sourceFile, sourceIn, sourceOut, timelineStart, timelineEnd, and durationSec.
     */
    buildEnhancementJobs(snapshot, masterJobId) {
      if (!snapshot || typeof snapshot !== 'object') {
        throw new Error("Valid snapshot object is required to build enhancement jobs");
      }

      const mJobId = masterJobId || ("job-" + Date.now().toString(36));
      const scope = snapshot.scope || "selected_clips";
      const seq = snapshot.sequence || {};
      const seqGuid = String(seq.guid || snapshot.sequenceGuid || "unknown_seq");
      const seqName = String(seq.name || snapshot.sequenceName || "Sequence");
      const jobs = [];

      if (scope === "selected_clips") {
        const rawClips = Array.isArray(snapshot.clips) ? snapshot.clips : [];
        for (let i = 0; i < rawClips.length; i++) {
          const clip = rawClips[i];
          const srcPath = clip.sourcePath || clip.mediaPath;
          if (!srcPath) continue;

          const startSec = (typeof clip.timelineStart === 'number') ? clip.timelineStart : (clip.startTimeSec || 0.0);
          const durSec = (typeof clip.duration === 'number') ? clip.duration : (clip.durationSec || 1.0);
          const inSec = (typeof clip.inPointSec === 'number') ? clip.inPointSec : 0.0;
          const outSec = (typeof clip.outPointSec === 'number') ? clip.outPointSec : (inSec + durSec);
          const tIdx = Number(clip.trackIndex !== undefined ? clip.trackIndex : 0);
          const tName = String(clip.trackName || `A${tIdx + 1}`);

          jobs.push({
            jobId: `${mJobId}_c${i}`,
            clipJobId: `${mJobId}_c${i}`,
            masterJobId: mJobId,
            batchId: mJobId,
            sourceFile: String(srcPath),
            sourcePath: String(srcPath),
            inPointSec: Number(inSec),
            outPointSec: Number(outSec),
            clipName: String(clip.clipName || clip.name || "Audio Clip"),
            timelineStart: Number(startSec),
            timelineEnd: Number(startSec + durSec),
            targetStartTime: Number(startSec),
            targetEndTime: Number(startSec + durSec),
            durationSec: Number(durSec),
            trackIndex: tIdx,
            trackName: tName,
            trackId: String(clip.trackId || `audio_track_${tIdx}`),
            clipId: String(clip.clipId || `clip_${i}`),
            clipIndex: i,
            projectItemId: String(clip.projectItemId || ""),
            sequenceGuid: seqGuid,
            sequenceName: seqName,
            scope: "selected_clips",
            fileSize: Number(clip.fileSize || 0),
            fileMtime: Number(clip.fileMtime || 0)
          });
        }

        console.log(`[Speechify Job Generator] scope=selected_clips clipsFound=${rawClips.length} jobsCreated=${jobs.length}`);
        return jobs;
      }

      // 'in_out' or 'full_sequence'
      const rangeStart = (scope === "in_out") ? Number(snapshot.inPointSec || 0.0) : 0.0;
      const rangeEnd = (scope === "in_out") ? Number(snapshot.outPointSec || snapshot.durationSec || 1e9) : 1e9;

      const tracks = Array.isArray(snapshot.tracks) && snapshot.tracks.length > 0
        ? snapshot.tracks
        : (snapshot.clips && snapshot.clips.length > 0
            ? [{ trackIndex: 0, trackName: "A1", trackId: "audio_track_0", clips: snapshot.clips, hasAudio: true }]
            : []);

      let totalClipsFound = 0;

      for (let t = 0; t < tracks.length; t++) {
        const trk = tracks[t];
        const tClips = Array.isArray(trk.clips) ? trk.clips : [];
        totalClipsFound += tClips.length;

        const tIdx = Number(trk.trackIndex !== undefined ? trk.trackIndex : t);
        const tName = String(trk.trackName || `A${tIdx + 1}`);
        const tId = String(trk.trackId || `audio_track_${tIdx}`);

        for (let c = 0; c < tClips.length; c++) {
          const clip = tClips[c];
          const srcPath = clip.sourcePath || clip.mediaPath;
          if (!srcPath) continue;

          const clipStart = Number((typeof clip.timelineStart === 'number') ? clip.timelineStart : (clip.startTimeSec || 0.0));
          const clipDur = Number((typeof clip.duration === 'number') ? clip.duration : (clip.durationSec || 1.0));
          const clipEnd = Number((typeof clip.timelineEnd === 'number') ? clip.timelineEnd : (clipStart + clipDur));
          const clipIn = Number(clip.inPointSec !== undefined ? clip.inPointSec : 0.0);

          // Calculate exact range intersection
          const effectiveStart = Math.max(clipStart, rangeStart);
          const effectiveEnd = Math.min(clipEnd, rangeEnd);

          if (effectiveEnd <= effectiveStart + 0.01) {
            // Clip does not intersect requested range
            continue;
          }

          const effectiveDuration = effectiveEnd - effectiveStart;
          const offsetFromClipStart = effectiveStart - clipStart;
          const sourceIn = clipIn + offsetFromClipStart;
          const sourceOut = sourceIn + effectiveDuration;
          const cName = clip.clipName || clip.name || "Audio Clip";
          const uniqueJobId = `${mJobId}_t${tIdx}_c${c}`;

          jobs.push({
            jobId: uniqueJobId,
            clipJobId: uniqueJobId,
            masterJobId: mJobId,
            batchId: mJobId,
            sourceFile: String(srcPath),
            sourcePath: String(srcPath),
            inPointSec: Number(sourceIn),
            outPointSec: Number(sourceOut),
            clipName: String(`${cName}_${tName}`),
            timelineStart: Number(effectiveStart),
            timelineEnd: Number(effectiveEnd),
            targetStartTime: Number(effectiveStart),
            targetEndTime: Number(effectiveEnd),
            durationSec: Number(effectiveDuration),
            trackIndex: tIdx,
            trackName: tName,
            trackId: tId,
            clipId: String(clip.clipId || `t${tIdx}_c${c}`),
            clipIndex: c,
            projectItemId: String(clip.projectItemId || ""),
            sequenceGuid: seqGuid,
            sequenceName: seqName,
            scope: scope,
            fileSize: Number(clip.fileSize || 0),
            fileMtime: Number(clip.fileMtime || 0)
          });
        }
      }

      console.log(`[Speechify Job Generator] scope=${scope} selectedTracks=${tracks.length} timelineAudioClipsFound=${totalClipsFound} jobsCreated=${jobs.length}`);

      // Log pre-flight plan
      for (let j = 0; j < jobs.length; j++) {
        const jb = jobs[j];
        console.log(`  [Plan Item ${j + 1}/${jobs.length}] ${jb.trackName} · ${jb.clipName}: timeline ${jb.timelineStart.toFixed(2)}s -> ${jb.timelineEnd.toFixed(2)}s (dur: ${jb.durationSec.toFixed(2)}s)`);
      }

      return jobs;
    }

    /**
     * Converts a track from snapshot into a pure primitive TrackJobPayload.
     * Guarantees zero host objects in multi-track job payloads.
     */
    toSafeTrackJobPayload(snapshot, track, masterBatchId, sourceFile) {
      if (!track || typeof track !== 'object') {
        throw new Error("Track object is required");
      }
      const seq = snapshot.sequence || {};
      const seqGuid = seq.guid || snapshot.sequenceGuid || "unknown_seq";
      const seqName = seq.name || snapshot.sequenceName || "Sequence";
      const trackIndex = Number(track.trackIndex !== undefined ? track.trackIndex : 0);
      const trackName = String(track.trackName || `A${trackIndex + 1}`);
      const trackJobId = `${masterBatchId}_t${trackIndex}`;
      const rangeStart = Number(track.rangeStart || 0.0);
      const rangeEnd = Number(track.rangeEnd || 0.0);
      const dur = Math.max(0.1, rangeEnd - rangeStart);

      return {
        clipJobId: String(trackJobId),
        masterJobId: String(masterBatchId),
        sourceFile: String(sourceFile || ""),
        inPointSec: 0.0,
        outPointSec: Number(dur),
        clipName: String(`${seqName}_${trackName}`),
        targetStartTime: Number(rangeStart),
        targetEndTime: Number(rangeEnd),
        durationSec: Number(dur),
        trackIndex: Number(trackIndex),
        trackId: String(track.trackId || `audio_track_${trackIndex}`),
        trackName: String(trackName),
        sequenceGuid: String(seqGuid),
        sequenceName: String(seqName),
        scope: String(snapshot.scope || "full_sequence"),
        clips: Array.isArray(track.clips) ? track.clips : []
      };
    }

    /**
     * Appends structured validation diagnostic entry to logs/context-validation.log.
     */
    logValidation(entry) {
      try {
        const logLine = `[${new Date().toISOString()}] [JOB: ${entry.jobId || 'pre-flight'}] [STAGE: ${entry.stage || 'validate'}] valid=${entry.valid} ` +
          `seq=${entry.sequenceGuid || 'none'} scope=${entry.scope || 'none'} ` +
          `${entry.errors && entry.errors.length > 0 ? 'ERRORS: ' + JSON.stringify(entry.errors) : 'OK'}\n`;

        if (fs && path) {
          let logDir = null;
          if (typeof window !== 'undefined' && window.SpeechifyPathManager) {
            const paths = window.SpeechifyPathManager.resolvePaths();
            logDir = paths.logsDir;
          }
          if (!logDir && typeof __dirname !== 'undefined') {
            logDir = path.join(__dirname, '..', '..', 'logs');
            if (!fs.existsSync(logDir)) {
              logDir = path.join(__dirname, '..', 'logs');
            }
          }
          if (logDir) {
            if (!fs.existsSync(logDir)) {
              fs.mkdirSync(logDir, { recursive: true });
            }
            const logFile = path.join(logDir, 'context-validation.log');
            fs.appendFileSync(logFile, logLine, 'utf8');
            return;
          }
        }
      } catch (err) {
        console.warn("[SpeechifyContextManager] Log write error:", err);
      }
    }
  }

  // Export singleton instance
  const instance = new ContextManager();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = instance;
  }
  if (typeof window !== 'undefined') {
    window.SpeechifyContextManager = instance;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
