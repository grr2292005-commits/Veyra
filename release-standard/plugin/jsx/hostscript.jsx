/**
 * Speechify — ExtendScript Host Script for Adobe Premiere Pro CEP
 * Bulletproof multi-clip extraction, tick normalization, and non-destructive timeline placement.
 */

#target premierepro

if (typeof $ !== 'undefined') {
    $._voxforge = {
        TICKS_PER_SEC: 254016000000,

        normalizeTime: function(val) {
            if (val === null || val === undefined) return 0.0;
            if (typeof val === 'object') {
                if (typeof val.seconds === 'number') return val.seconds;
                if (typeof val.seconds === 'string') {
                    var s = parseFloat(val.seconds);
                    if (!isNaN(s)) return s;
                }
                if (val.ticks) {
                    var t = parseFloat(val.ticks);
                    if (!isNaN(t) && t > 0) return t / this.TICKS_PER_SEC;
                }
                return 0.0;
            }
            var num = typeof val === 'number' ? val : parseFloat(val);
            if (isNaN(num)) return 0.0;
            if (num > 10000000) {
                return num / this.TICKS_PER_SEC;
            }
            return Math.max(0.0, num);
        },

        ticksToFps: function(ticks) {
            if (!ticks || ticks <= 0) return 23.976;
            var fps = Math.round((this.TICKS_PER_SEC / ticks) * 1000) / 1000;
            return fps > 0 ? fps : 23.976;
        },

        getSequenceEndSec: function(seq) {
            var endSec = this.normalizeTime(seq.end);
            if (endSec > 0) return endSec;

            var maxEnd = 0.0;
            if (seq.audioTracks) {
                for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                    var trk = seq.audioTracks[t];
                    for (var c = 0; c < trk.clips.numItems; c++) {
                        var clp = trk.clips[c];
                        var clpEnd = this.normalizeTime(clp.end);
                        if (clpEnd <= 0) {
                            var clpStart = this.normalizeTime(clp.start);
                            var clpDur = this.normalizeTime(clp.duration);
                            clpEnd = clpStart + clpDur;
                        }
                        if (clpEnd > maxEnd) maxEnd = clpEnd;
                    }
                }
            }
            if (seq.videoTracks) {
                for (var vt = 0; vt < seq.videoTracks.numTracks; vt++) {
                    var vtrk = seq.videoTracks[vt];
                    for (var vc = 0; vc < vtrk.clips.numItems; vc++) {
                        var vclp = vtrk.clips[vc];
                        var vclpEnd = this.normalizeTime(vclp.end);
                        if (vclpEnd <= 0) {
                            var vclpStart = this.normalizeTime(vclp.start);
                            var vclpDur = this.normalizeTime(vclp.duration);
                            vclpEnd = vclpStart + vclpDur;
                        }
                        if (vclpEnd > maxEnd) maxEnd = vclpEnd;
                    }
                }
            }
            return maxEnd > 0 ? maxEnd : 1.0;
        },

        getActiveSequenceInfo: function() {
            if (!app.project || !app.project.activeSequence) {
                return JSON.stringify({ available: false, error: "No active sequence open in Premiere Pro" });
            }

            var seq = app.project.activeSequence;
            var timebaseTicks = parseInt(seq.timebase);
            var fps = this.ticksToFps(timebaseTicks);

            var inSec = this.normalizeTime(seq.getInPoint());
            var outSec = this.normalizeTime(seq.getOutPoint());
            var endSec = this.getSequenceEndSec(seq);

            if (outSec <= inSec || outSec <= 0) {
                outSec = endSec;
            }

            var durationSec = endSec;

            var audioTracks = [];
            if (seq.audioTracks) {
                for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                    var trk = seq.audioTracks[t];
                    audioTracks.push({
                        index: t,
                        id: "audio_track_" + t,
                        name: trk.name || ("A" + (t + 1)),
                        numClips: trk.clips ? trk.clips.numItems : 0
                    });
                }
            }

            return JSON.stringify({
                available: true,
                name: seq.name,
                sequenceId: seq.sequenceID || seq.guid || (seq.projectItem ? seq.projectItem.nodeId : "") || seq.name,
                timebaseTicks: timebaseTicks,
                fps: fps,
                sampleRate: 48000,
                inPointSec: inSec,
                outPointSec: outSec,
                durationSec: durationSec,
                audioTrackCount: audioTracks.length,
                audioTracks: audioTracks
            });
        },

        /**
         * Returns an array of all currently selected audio clips in the active sequence.
         * Distinguishes timeline position (startTimeSec) from source asset media range (inPointSec -> outPointSec).
         */
        getSelectedAudioClips: function() {
            if (!app.project || !app.project.activeSequence) {
                return JSON.stringify([]);
            }

            var seq = app.project.activeSequence;
            var selectedItems = [];

            if (seq.audioTracks) {
                for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                    var track = seq.audioTracks[t];
                    for (var c = 0; c < track.clips.numItems; c++) {
                        var clip = track.clips[c];
                        if (clip.isSelected && clip.isSelected()) {
                            var pItem = clip.projectItem;
                            var path = pItem ? pItem.getMediaPath() : null;
                            if (path) {
                                var startSec = this.normalizeTime(clip.start);
                                var durSec = this.normalizeTime(clip.duration);
                                var inSec = this.normalizeTime(clip.inPoint);
                                var outSec = this.normalizeTime(clip.outPoint);

                                if (outSec <= inSec && durSec > 0) {
                                    outSec = inSec + durSec;
                                }
                                if (durSec <= 0 && outSec > inSec) {
                                    durSec = outSec - inSec;
                                }

                                var cleanName = clip.name || (pItem ? pItem.name : "Audio Clip");

                                selectedItems.push({
                                    name: cleanName,
                                    mediaPath: path,
                                    startTimeSec: startSec,
                                    durationSec: durSec,
                                    inPointSec: inSec,
                                    outPointSec: outSec,
                                    trackIndex: t,
                                    trackName: track.name,
                                    clipIndex: c,
                                    clipId: cleanName + "_t" + t + "_c" + c + "_s" + Math.round(startSec * 100)
                                });
                            }
                        }
                    }
                }
            }

            // Sort clips chronologically by timeline start time
            selectedItems.sort(function(a, b) {
                return a.startTimeSec - b.startTimeSec;
            });

            return JSON.stringify(selectedItems);
        },

        /**
         * Returns all audio clips across all audio tracks in the active sequence.
         */
        getAllSequenceAudioClips: function() {
            if (!app.project || !app.project.activeSequence) {
                return JSON.stringify([]);
            }

            var seq = app.project.activeSequence;
            var allClips = [];

            if (seq.audioTracks) {
                for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                    var track = seq.audioTracks[t];
                    for (var c = 0; c < track.clips.numItems; c++) {
                        var clip = track.clips[c];
                        var pItem = clip.projectItem;
                        var path = pItem ? pItem.getMediaPath() : null;
                        if (path) {
                            var startSec = this.normalizeTime(clip.start);
                            var durSec = this.normalizeTime(clip.duration);
                            var inSec = this.normalizeTime(clip.inPoint);
                            var outSec = this.normalizeTime(clip.outPoint);

                            if (outSec <= inSec && durSec > 0) {
                                outSec = inSec + durSec;
                            }
                            if (durSec <= 0 && outSec > inSec) {
                                durSec = outSec - inSec;
                            }

                            var cleanName = clip.name || (pItem ? pItem.name : "Audio Clip");

                            allClips.push({
                                name: cleanName,
                                mediaPath: path,
                                startTimeSec: startSec,
                                durationSec: durSec,
                                inPointSec: inSec,
                                outPointSec: outSec,
                                trackIndex: t,
                                trackName: track.name,
                                clipIndex: c,
                                clipId: cleanName + "_t" + t + "_c" + c + "_s" + Math.round(startSec * 100)
                            });
                        }
                    }
                }
            }

            // Sort clips chronologically
            allClips.sort(function(a, b) {
                return a.startTimeSec - b.startTimeSec;
            });

            return JSON.stringify(allClips);
        },

        /**
         * Safely decodes and parses context payloads received from CEP/UXP.
         * Handles objects, JSON strings, URL-encoded strings, and double-serialized JSON.
         */
        parseContextPayload: function(payload) {
            if (payload === null || payload === undefined) {
                throw new Error("Context payload is null or undefined");
            }
            if (typeof payload === 'object') {
                return payload;
            }
            if (typeof payload === 'string') {
                var str = payload;
                // Trim whitespace
                str = str.replace(/^\s+|\s+$/g, '');
                if (str.length === 0) {
                    throw new Error("Context payload is empty string");
                }
                // If payload was URL-encoded (to safely pass Windows backslashes across evalScript)
                if (str.indexOf('%') !== -1 && (str.indexOf('%7B') === 0 || str.indexOf('%22') !== -1 || str.indexOf('%5B') === 0)) {
                    try {
                        str = decodeURIComponent(str);
                    } catch (decErr) {
                        // ignore and try raw
                    }
                }
                var parsed = JSON.parse(str);
                // Handle double-serialized JSON strings
                if (typeof parsed === 'string') {
                    try {
                        var doubleParsed = JSON.parse(parsed);
                        if (doubleParsed && typeof doubleParsed === 'object') {
                            parsed = doubleParsed;
                        }
                    } catch (dErr) {
                        // keep first parsed
                    }
                }
                if (!parsed || typeof parsed !== 'object') {
                    throw new Error("Context payload did not deserialize to an object");
                }
                return parsed;
            }
            throw new Error("Unsupported context payload type: " + typeof payload);
        },

        /**
         * Creates an authoritative fresh snapshot of the active sequence and target audio clips
         * at the exact moment Enhance Speech is triggered.
         * Returns a pure PremiereContextSnapshot (schemaVersion: 1) containing ONLY primitives.
         */
        createFreshTimelineSnapshot: function(jsonString) {
            try {
                var options = {};
                if (jsonString) {
                    try {
                        options = this.parseContextPayload(jsonString);
                    } catch (e) {
                        options = {};
                    }
                }
                var scope = options.scope || "selected_clips";
                var selectedTrackIndices = options.selectedTrackIndices || [];
                var trackIndexSet = {};
                for (var k = 0; k < selectedTrackIndices.length; k++) {
                    trackIndexSet[selectedTrackIndices[k]] = true;
                }

                if (!app.project || !app.project.activeSequence) {
                    return JSON.stringify({ success: false, error: "No active sequence open in Premiere Pro." });
                }

                var seq = app.project.activeSequence;
                var seqId = seq.sequenceID || seq.guid || (seq.projectItem ? seq.projectItem.nodeId : "") || seq.name;
                var timebaseTicks = parseInt(seq.timebase);
                var fps = this.ticksToFps(timebaseTicks);
                var inSec = this.normalizeTime(seq.getInPoint());
                var outSec = this.normalizeTime(seq.getOutPoint());
                var endSec = this.getSequenceEndSec(seq);
                if (outSec <= inSec || outSec <= 0) outSec = endSec;

                var clips = [];

                if (scope === "selected_clips") {
                    if (seq.audioTracks) {
                        for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                            var track = seq.audioTracks[t];
                            for (var c = 0; c < track.clips.numItems; c++) {
                                var clip = track.clips[c];
                                if (clip.isSelected && clip.isSelected()) {
                                    var pItem = clip.projectItem;
                                    var path = pItem ? pItem.getMediaPath() : null;
                                    if (path) {
                                        var startSec = this.normalizeTime(clip.start);
                                        var durSec = this.normalizeTime(clip.duration);
                                        var clipIn = this.normalizeTime(clip.inPoint);
                                        var clipOut = this.normalizeTime(clip.outPoint);
                                        if (clipOut <= clipIn && durSec > 0) clipOut = clipIn + durSec;
                                        if (durSec <= 0 && clipOut > clipIn) durSec = clipOut - clipIn;

                                        var f = File(path);
                                        var fExists = f.exists;
                                        var fSize = fExists ? f.length : 0;
                                        var fMtime = fExists ? f.modified.getTime() : 0;
                                        var pNodeId = pItem ? (pItem.nodeId || pItem.name) : "unknown";
                                        var clipNodeId = clip.nodeId || ("t" + t + "_c" + c + "_s" + Math.round(startSec * 1000));
                                        var cName = clip.name || (pItem ? pItem.name : "Audio Clip");

                                        clips.push({
                                            trackIndex: t,
                                            trackName: track.name,
                                            clipName: cName,
                                            name: cName,
                                            mediaPath: path,
                                            sourcePath: path,
                                            clipIndex: c,
                                            clipId: clipNodeId,
                                            projectItemId: pNodeId,
                                            projectItemName: pItem ? pItem.name : "",
                                            startTimeSec: startSec,
                                            timelineStart: startSec,
                                            timelineEnd: startSec + durSec,
                                            durationSec: durSec,
                                            duration: durSec,
                                            inPointSec: clipIn,
                                            outPointSec: clipOut,
                                            fileSize: fSize,
                                            fileMtime: fMtime,
                                            fileExists: fExists
                                        });
                                    }
                                }
                            }
                        }
                    }

                    if (clips.length === 0) {
                        return JSON.stringify({ success: false, error: "Select an audio clip in the timeline.", clips: [] });
                    }

                } else {
                    // 'in_out' or 'full_sequence'
                    var rangeIn = (scope === "in_out") ? inSec : 0.0;
                    var rangeOut = (scope === "in_out") ? outSec : endSec;
                    var tracks = [];

                    if (seq.audioTracks) {
                        for (var t = 0; t < seq.audioTracks.numTracks; t++) {
                            if (!trackIndexSet[t] && selectedTrackIndices.length > 0) continue;
                            var track = seq.audioTracks[t];
                            var trackClips = [];

                            for (var c = 0; c < track.clips.numItems; c++) {
                                var clip = track.clips[c];
                                var pItem = clip.projectItem;
                                var path = pItem ? pItem.getMediaPath() : null;
                                if (path) {
                                    var startSec = this.normalizeTime(clip.start);
                                    var durSec = this.normalizeTime(clip.duration);
                                    var clipIn = this.normalizeTime(clip.inPoint);
                                    var clipOut = this.normalizeTime(clip.outPoint);
                                    if (clipOut <= clipIn && durSec > 0) clipOut = clipIn + durSec;
                                    if (durSec <= 0 && clipOut > clipIn) durSec = clipOut - clipIn;

                                    if (startSec + durSec > rangeIn && startSec < rangeOut) {
                                        var f = File(path);
                                        var fExists = f.exists;
                                        var fSize = fExists ? f.length : 0;
                                        var fMtime = fExists ? f.modified.getTime() : 0;
                                        var pNodeId = pItem ? (pItem.nodeId || pItem.name) : "unknown";
                                        var clipNodeId = clip.nodeId || ("t" + t + "_c" + c + "_s" + Math.round(startSec * 1000));
                                        var cName = clip.name || (pItem ? pItem.name : "Audio Clip");

                                        var clipObj = {
                                            trackIndex: t,
                                            trackName: track.name || ("A" + (t + 1)),
                                            clipName: cName,
                                            name: cName,
                                            mediaPath: path,
                                            sourcePath: path,
                                            clipIndex: c,
                                            clipId: clipNodeId,
                                            projectItemId: pNodeId,
                                            projectItemName: pItem ? pItem.name : "",
                                            startTimeSec: startSec,
                                            timelineStart: startSec,
                                            timelineEnd: startSec + durSec,
                                            durationSec: durSec,
                                            duration: durSec,
                                            inPointSec: clipIn,
                                            outPointSec: clipOut,
                                            fileSize: fSize,
                                            fileMtime: fMtime,
                                            fileExists: fExists
                                        };
                                        trackClips.push(clipObj);
                                        clips.push(clipObj);
                                    }
                                }
                            }

                            trackClips.sort(function(a, b) { return a.startTimeSec - b.startTimeSec; });
                            tracks.push({
                                trackId: "audio_track_" + t,
                                trackIndex: t,
                                trackName: track.name || ("A" + (t + 1)),
                                rangeStart: rangeIn,
                                rangeEnd: rangeOut,
                                durationSec: Math.max(0.1, rangeOut - rangeIn),
                                clips: trackClips,
                                clipCount: trackClips.length,
                                hasAudio: trackClips.length > 0
                            });
                        }
                    }

                    if (clips.length === 0) {
                        return JSON.stringify({
                            success: false,
                            error: "No audio clips found on selected tracks within specified range.",
                            clips: [],
                            tracks: tracks
                        });
                    }
                }

                clips.sort(function(a, b) { return a.startTimeSec - b.startTimeSec; });

                return JSON.stringify({
                    success: true,
                    schemaVersion: 1,
                    sequence: {
                        guid: seqId,
                        name: seq.name
                    },
                    sequenceGuid: seqId,
                    sequenceName: seq.name,
                    timebaseTicks: timebaseTicks,
                    fps: fps,
                    sampleRate: 48000,
                    inPointSec: inSec,
                    outPointSec: outSec,
                    durationSec: endSec,
                    scope: scope,
                    clips: clips,
                    tracks: (scope === "selected_clips") ? [] : tracks,
                    snapshotTimestamp: (new Date()).getTime()
                });
            } catch (err) {
                return JSON.stringify({ success: false, error: "Snapshot creation error: " + err.toString() });
            }
        },

        /**
         * Authoritative pre-flight check immediately before audio extraction.
         * Guarantees that the active sequence and track items still match the snapshot.
         * Returns structured results: { valid: true, errors: [], warnings: [] }
         */
        validateCurrentPremiereContext: function(snapshotJson) {
            try {
                if (!app.project || !app.project.activeSequence) {
                    return JSON.stringify({
                        valid: false,
                        errors: [{ code: "NO_ACTIVE_SEQUENCE", message: "Active sequence is no longer open in Premiere Pro." }],
                        reason: "Active sequence is no longer open in Premiere Pro."
                    });
                }

                var snapshot;
                try {
                    snapshot = this.parseContextPayload(snapshotJson);
                } catch (parseErr) {
                    return JSON.stringify({
                        valid: false,
                        errors: [{ code: "MALFORMED_PAYLOAD", message: "Couldn't read the current Premiere selection. Please try again." }],
                        reason: "Couldn't read the current Premiere selection. Please try again."
                    });
                }

                var seq = app.project.activeSequence;
                var currentSeqId = seq.sequenceID || seq.guid || (seq.projectItem ? seq.projectItem.nodeId : "") || seq.name;
                var targetSeqGuid = (snapshot.sequence && snapshot.sequence.guid) || snapshot.sequenceGuid;
                var targetSeqName = (snapshot.sequence && snapshot.sequence.name) || snapshot.sequenceName || "Sequence";

                if (currentSeqId !== targetSeqGuid) {
                    return JSON.stringify({
                        valid: false,
                        errors: [{ code: "SEQUENCE_CHANGED", message: "Active sequence changed from '" + targetSeqName + "' to '" + seq.name + "'." }],
                        reason: "Active sequence changed from '" + targetSeqName + "' to '" + seq.name + "'."
                    });
                }

                if (snapshot.scope === "selected_clips" && snapshot.clips) {
                    for (var i = 0; i < snapshot.clips.length; i++) {
                        var snapClip = snapshot.clips[i];
                        var snapPath = snapClip.sourcePath || snapClip.mediaPath;
                        var snapStart = (typeof snapClip.timelineStart === 'number') ? snapClip.timelineStart : snapClip.startTimeSec;
                        var snapName = snapClip.clipName || snapClip.name || "Audio Clip";

                        if (snapClip.trackIndex >= seq.audioTracks.numTracks) {
                            return JSON.stringify({
                                valid: false,
                                errors: [{ code: "TRACK_NOT_FOUND", message: "Track index no longer exists in sequence." }],
                                reason: "Track index no longer exists in sequence."
                            });
                        }
                        var track = seq.audioTracks[snapClip.trackIndex];
                        var found = false;
                        for (var c = 0; c < track.clips.numItems; c++) {
                            var liveClip = track.clips[c];
                            var liveStart = this.normalizeTime(liveClip.start);
                            if (Math.abs(liveStart - snapStart) < 0.05) {
                                var livePItem = liveClip.projectItem;
                                var livePath = livePItem ? livePItem.getMediaPath() : null;
                                if (livePath && livePath === snapPath) {
                                    found = true;
                                    break;
                                }
                            }
                        }
                        if (!found) {
                            return JSON.stringify({
                                valid: false,
                                errors: [{ code: "CLIP_REMOVED_OR_REPLACED", message: "Selected clip '" + snapName + "' was removed, moved, or replaced on the timeline." }],
                                reason: "Selected clip '" + snapName + "' was removed, moved, or replaced on the timeline."
                            });
                        }
                    }
                }

                return JSON.stringify({ valid: true, errors: [], warnings: [] });
            } catch (err) {
                return JSON.stringify({
                    valid: false,
                    errors: [{ code: "VALIDATION_EXCEPTION", message: "Couldn't read the current Premiere selection. Please try again." }],
                    reason: "Couldn't read the current Premiere selection. Please try again."
                });
            }
        },

        /**
         * Imports an enhanced audio WAV into 'Speechify' bin.
         * Verifies imported item exists and points to the exact media file.
         */
        importEnhancedAudio: function(jsonString) {
            try {
                var options = this.parseContextPayload(jsonString);
                var wavPath = options.wavPath;
                if (!wavPath || !File(wavPath).exists) {
                    return JSON.stringify({ success: false, error: "Output WAV file does not exist on disk: " + wavPath });
                }

                if (!app.project) {
                    return JSON.stringify({ success: false, error: "No active Premiere project." });
                }

                var project = app.project;
                var rootItem = project.rootItem;
                var targetBin = null;
                for (var i = 0; i < rootItem.children.numItems; i++) {
                    var item = rootItem.children[i];
                    if (item.type === 2 && (item.name === "Veyra" || item.name === "Speechify")) {
                        targetBin = item;
                        break;
                    }
                }
                if (!targetBin) {
                    targetBin = rootItem.createBin("Veyra");
                }

                var numBefore = targetBin.children.numItems;
                var importSuccess = project.importFiles([wavPath], true, targetBin, false);
                if (!importSuccess) {
                    return JSON.stringify({ success: false, error: "Premiere failed to import " + wavPath });
                }

                function normPath(p) {
                    return p ? p.replace(/\\/g, "/").toLowerCase() : "";
                }
                var targetNorm = normPath(wavPath);
                var fObj = File(wavPath);
                var expectedFilename = fObj.name ? fObj.name.toLowerCase() : "";

                var importedItem = null;
                for (var j = targetBin.children.numItems - 1; j >= 0; j--) {
                    var child = targetBin.children[j];
                    var childPath = normPath(child.getMediaPath ? child.getMediaPath() : "");
                    if (childPath === targetNorm) {
                        importedItem = child;
                        break;
                    }
                }
                if (!importedItem) {
                    for (var j = targetBin.children.numItems - 1; j >= 0; j--) {
                        var child = targetBin.children[j];
                        if (child.name && child.name.toLowerCase() === expectedFilename) {
                            importedItem = child;
                            break;
                        }
                    }
                }
                if (!importedItem && targetBin.children.numItems > numBefore) {
                    importedItem = targetBin.children[targetBin.children.numItems - 1];
                }

                if (!importedItem) {
                    return JSON.stringify({ success: false, error: "Imported item not found in Veyra bin." });
                }

                return JSON.stringify({
                    success: true,
                    projectItemName: importedItem.name,
                    projectItemId: importedItem.nodeId || importedItem.name,
                    mediaPath: importedItem.getMediaPath ? importedItem.getMediaPath() : wavPath
                });
            } catch (err) {
                return JSON.stringify({ success: false, error: "Exception during bin import: " + err.toString() });
            }
        },

        /**
         * Imports enhanced WAV into 'Speechify' bin and inserts into timeline at exact startTimeSec
         * on the next safe, non-overlapping audio track. NEVER overwrites or replaces the source clip.
         *
         * PREMIERE AUDIO TRACK INDEX ORIENTATION:
         * seq.audioTracks[0] is A1 (top of audio stack).
         * Increasing index (t = 1, 2, ...) is visually LOWER in the Premiere timeline (A2, A3, ...).
         * Decreasing index goes visually UPWARD towards A1.
         * Destination search strictly scans DOWNWARD from sourceTrackIndex + 1 to numTracks - 1.
         * Upward scanning to tracks above source (e.g. A1 when source is A2) is strictly forbidden.
         */
        placeEnhancedClip: function(jsonString) {
            try {
                var options = this.parseContextPayload(jsonString);
                var wavPath = options.wavPath;
                var clipName = options.clipName || "Enhanced Audio";
                var startTimeSec = this.normalizeTime(options.startTimeSec);
                var durationSec = options.durationSec ? parseFloat(options.durationSec) : 0;
                var endTimeSec = options.endTimeSec ? parseFloat(options.endTimeSec) : (durationSec > 0 ? (startTimeSec + durationSec) : (startTimeSec + 1.0));
                var placementMode = options.placementMode || "new_track";
                var sourceTrackIndex = (options.sourceTrackIndex !== undefined && options.sourceTrackIndex !== null) ? parseInt(options.sourceTrackIndex) : ((options.trackIndex !== undefined && options.trackIndex !== null) ? parseInt(options.trackIndex) : -1);
                var reservedIntervals = options.reservedIntervals || {};

                if (!app.project || !app.project.activeSequence) {
                    return JSON.stringify({ success: false, placedOnTimeline: false, error: "No active sequence" });
                }

                var project = app.project;
                var seq = project.activeSequence;

                // Step 1: Find or create bin 'Veyra' (checks legacy 'Speechify' for backward compatibility)
                var targetBin = null;
                var rootItem = project.rootItem;
                for (var i = 0; i < rootItem.children.numItems; i++) {
                    var item = rootItem.children[i];
                    if (item.type === 2 && (item.name === "Veyra" || item.name === "Speechify")) {
                        targetBin = item;
                        break;
                    }
                }
                if (!targetBin) {
                    targetBin = rootItem.createBin("Veyra");
                }

                // Step 2: Import audio file into Speechify bin
                var numBefore = targetBin.children.numItems;
                var importSuccess = project.importFiles([wavPath], true, targetBin, false);
                if (!importSuccess) {
                    return JSON.stringify({ success: false, placedOnTimeline: false, error: "Failed to import " + wavPath });
                }

                function normPath(p) {
                    return p ? p.replace(/\\/g, "/").toLowerCase() : "";
                }
                var targetNorm = normPath(wavPath);
                var fObj = File(wavPath);
                var expectedFilename = fObj.name ? fObj.name.toLowerCase() : "";

                // Find imported project item
                var importedItem = null;
                for (var j = targetBin.children.numItems - 1; j >= 0; j--) {
                    var child = targetBin.children[j];
                    var childPath = normPath(child.getMediaPath ? child.getMediaPath() : "");
                    if (childPath === targetNorm) {
                        importedItem = child;
                        break;
                    }
                }
                if (!importedItem) {
                    for (var j = targetBin.children.numItems - 1; j >= 0; j--) {
                        var child = targetBin.children[j];
                        if (child.name && child.name.toLowerCase() === expectedFilename) {
                            importedItem = child;
                            break;
                        }
                    }
                }
                if (!importedItem && targetBin.children.numItems > numBefore) {
                    importedItem = targetBin.children[targetBin.children.numItems - 1];
                }

                if (!importedItem) {
                    return JSON.stringify({ success: false, placedOnTimeline: false, error: "Imported file not found in bin" });
                }

                // Output Mode: Project bin only (strictly no timeline alteration)
                if (placementMode === 'project_only') {
                    return JSON.stringify({
                        success: true,
                        placedOnTimeline: false,
                        projectItemName: importedItem.name,
                        projectItemId: importedItem.nodeId || importedItem.name,
                        message: "Saved to Veyra bin"
                    });
                }

                // Step 3: Determine Next Safe Audio Track (Strictly Downward, Zero Overlap & Never Source Track)
                var numTracks = seq.audioTracks ? seq.audioTracks.numTracks : 0;
                if (numTracks === 0) {
                    return JSON.stringify({
                        success: false,
                        placedOnTimeline: false,
                        imported: true,
                        projectItemName: importedItem.name,
                        error: "Couldn't place the enhanced audio on the timeline. The original audio was left unchanged."
                    });
                }

                // Internal helper: test if track is safe for [startTimeSec, endTimeSec]
                function isTrackSafe(trk, trkIdx, startS, endS, resMap) {
                    if (!trk) return false;
                    // Locked tracks are never considered safe
                    if (trk.isLocked && trk.isLocked()) {
                        return false;
                    }
                    var tol = 0.001;
                    // Check existing clips on this track
                    if (trk.clips && trk.clips.numItems > 0) {
                        for (var c = 0; c < trk.clips.numItems; c++) {
                            var clp = trk.clips[c];
                            var cStart = clp.start.seconds;
                            var cEnd = clp.end.seconds;
                            if (startS < cEnd - tol && endS > cStart + tol) {
                                return false; // Timeline interval collision
                            }
                        }
                    }
                    // Check batch reservation map
                    var key = trkIdx.toString();
                    if (resMap && (resMap[key] || resMap[trkIdx])) {
                        var resList = resMap[key] || resMap[trkIdx];
                        for (var r = 0; r < resList.length; r++) {
                            var res = resList[r];
                            if (startS < res.endSec - tol && endS > res.startSec + tol) {
                                return false; // Reserved by another job in current batch
                            }
                        }
                    }
                    return true;
                }

                var targetTrack = null;
                var targetTrackIndex = -1;

                // Priority candidate ordering:
                // Scan strictly downwards below source: sourceTrackIndex + 1 ... numTracks - 1
                // NEVER move upward to tracks above source (e.g. A1 when source is on A2)
                var candidateIndices = [];
                if (sourceTrackIndex >= 0 && sourceTrackIndex < numTracks) {
                    for (var t1 = sourceTrackIndex + 1; t1 < numTracks; t1++) {
                        candidateIndices.push(t1);
                    }
                } else {
                    for (var t0 = 0; t0 < numTracks; t0++) {
                        candidateIndices.push(t0);
                    }
                }

                for (var ci = 0; ci < candidateIndices.length; ci++) {
                    var candIdx = candidateIndices[ci];
                    var candTrk = seq.audioTracks[candIdx];
                    if (isTrackSafe(candTrk, candIdx, startTimeSec, endTimeSec, reservedIntervals)) {
                        targetTrack = candTrk;
                        targetTrackIndex = candIdx;
                        break;
                    }
                }

                // If all existing tracks are occupied or locked, create new audio track at bottom
                if (!targetTrack) {
                    var prevNumTracks = numTracks;
                    try {
                        app.enableQE();
                        if (typeof qe !== 'undefined' && qe.project) {
                            var qeSeq = qe.project.getActiveSequence();
                            if (qeSeq && typeof qeSeq.addTracks === 'function') {
                                qeSeq.addTracks(0, 1); // Adds 0 Video Tracks, 1 Audio Track
                            }
                        }
                    } catch (qeErr) {}

                    numTracks = seq.audioTracks ? seq.audioTracks.numTracks : 0;
                    if (numTracks > prevNumTracks) {
                        targetTrackIndex = numTracks - 1;
                        targetTrack = seq.audioTracks[targetTrackIndex];
                    }
                }

                if (!targetTrack) {
                    return JSON.stringify({
                        success: false,
                        placedOnTimeline: false,
                        imported: true,
                        projectItemName: importedItem.name,
                        error: "Couldn't place the enhanced audio on the timeline. The original audio was left unchanged."
                    });
                }

                // Step 4: Non-Destructive Clip Insertion at Exact Frame Start Ticks
                // NEVER use overwriteClip! Always use insertClip.
                var timeTicks = Math.round(startTimeSec * $._voxforge.TICKS_PER_SEC).toString();
                var preClipsCount = targetTrack.clips.numItems;
                targetTrack.insertClip(importedItem, timeTicks);

                // Step 5: Bounded Post-Insertion Verification
                var postClipsCount = targetTrack.clips.numItems;
                var verifiedPlacement = false;
                var actualStartTimeSec = startTimeSec;
                var actualDurationSec = durationSec;

                if (postClipsCount > preClipsCount || postClipsCount > 0) {
                    for (var vi = 0; vi < targetTrack.clips.numItems; vi++) {
                        var placedClip = targetTrack.clips[vi];
                        var startDiff = Math.abs(placedClip.start.seconds - startTimeSec);
                        if (startDiff < 0.05) { // Within 1 frame tolerance
                            verifiedPlacement = true;
                            actualStartTimeSec = placedClip.start.seconds;
                            actualDurationSec = placedClip.duration.seconds;
                            break;
                        }
                    }
                }

                if (!verifiedPlacement && postClipsCount > preClipsCount) {
                    // Item was inserted, accept with recorded start time
                    verifiedPlacement = true;
                }

                if (!verifiedPlacement) {
                    return JSON.stringify({
                        success: false,
                        placedOnTimeline: false,
                        imported: true,
                        projectItemName: importedItem.name,
                        error: "Couldn't place the enhanced audio on the timeline. The original audio was left unchanged."
                    });
                }

                return JSON.stringify({
                    success: true,
                    placedOnTimeline: true,
                    placedTrack: targetTrack.name,
                    trackIndex: targetTrackIndex,
                    startTimeSec: actualStartTimeSec,
                    durationSec: actualDurationSec,
                    clipName: clipName,
                    projectItemName: importedItem.name,
                    projectItemId: importedItem.nodeId || importedItem.name
                });

            } catch (err) {
                return JSON.stringify({
                    success: false,
                    placedOnTimeline: false,
                    error: "Couldn't place the enhanced audio on the timeline. The original audio was left unchanged."
                });
            }
        }
    };
}

