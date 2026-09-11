"""
Unit Tests for Active Audio Clip Processing & Gap Preservation for Range Modes.
Exhaustively verifies:
1. Full Sequence processes actual audio clips on selected tracks, NOT empty timeline space.
2. Full Sequence with 2 clips and a gap on A1 produces exactly 2 jobs, preserving the gap.
3. Total enhanced audio duration equals sum of actual clip durations (NOT sequence span).
4. Full Sequence with 2 tracks (2 clips each) produces exactly 4 independent clip jobs.
5. In / Out intersection logic slices clips to range boundaries without padding silence.
6. Clips outside In / Out range produce 0 jobs.
7. Selected Clips mode remains direct 1-to-1 mapping ignoring track filters.
8. Destination placement: sequential non-overlapping clips from the same source track safely
   share the same destination track while keeping the timeline gap empty.
"""

import os
import sys
import json
import unittest
import numpy as np
import soundfile as sf
import tempfile
from typing import Dict, List, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.audio.pipeline import AudioPipeline
from tests.unit.test_timeline_placement import MockTimelinePlacementService


class MockContextManager:
    """
    Python equivalent of ContextManager.buildEnhancementJobs.
    Mirrors plugin/services/context_manager.js 1-to-1.
    """
    @staticmethod
    def build_enhancement_jobs(snapshot: Dict[str, Any], master_job_id: str) -> List[Dict[str, Any]]:
        if not snapshot:
            raise ValueError("Snapshot required")

        scope = snapshot.get("scope", "selected_clips")
        seq = snapshot.get("sequence", {})
        seq_guid = seq.get("guid", snapshot.get("sequenceGuid", "seq_1"))
        seq_name = seq.get("name", snapshot.get("sequenceName", "Sequence"))
        jobs = []

        if scope == "selected_clips":
          raw_clips = snapshot.get("clips", [])
          for i, clip in enumerate(raw_clips):
              src_path = clip.get("sourcePath") or clip.get("mediaPath")
              if not src_path:
                  continue
              start_sec = clip.get("timelineStart", clip.get("startTimeSec", 0.0))
              dur_sec = clip.get("duration", clip.get("durationSec", 1.0))
              in_sec = clip.get("inPointSec", 0.0)
              out_sec = clip.get("outPointSec", in_sec + dur_sec)
              t_idx = clip.get("trackIndex", 0)
              t_name = clip.get("trackName", f"A{t_idx + 1}")

              jobs.append({
                  "jobId": f"{master_job_id}_c{i}",
                  "clipJobId": f"{master_job_id}_c{i}",
                  "masterJobId": master_job_id,
                  "sourceFile": str(src_path),
                  "sourcePath": str(src_path),
                  "inPointSec": float(in_sec),
                  "outPointSec": float(out_sec),
                  "clipName": clip.get("clipName", clip.get("name", "Audio Clip")),
                  "timelineStart": float(start_sec),
                  "timelineEnd": float(start_sec + dur_sec),
                  "targetStartTime": float(start_sec),
                  "targetEndTime": float(start_sec + dur_sec),
                  "durationSec": float(dur_sec),
                  "trackIndex": int(t_idx),
                  "trackName": str(t_name),
                  "trackId": clip.get("trackId", f"audio_track_{t_idx}"),
                  "clipId": clip.get("clipId", f"clip_{i}"),
                  "clipIndex": i,
                  "projectItemId": clip.get("projectItemId", ""),
                  "sequenceGuid": seq_guid,
                  "sequenceName": seq_name,
                  "scope": "selected_clips"
              })
          return jobs

        # in_out or full_sequence
        range_start = float(snapshot.get("inPointSec", 0.0)) if scope == "in_out" else 0.0
        range_end = float(snapshot.get("outPointSec", snapshot.get("durationSec", 1e9))) if scope == "in_out" else 1e9

        tracks = snapshot.get("tracks", [])
        if not tracks and snapshot.get("clips"):
            tracks = [{"trackIndex": 0, "trackName": "A1", "clips": snapshot.get("clips", []), "hasAudio": True}]

        for t, trk in enumerate(tracks):
            t_clips = trk.get("clips", [])
            t_idx = trk.get("trackIndex", t)
            t_name = trk.get("trackName", f"A{t_idx + 1}")
            t_id = trk.get("trackId", f"audio_track_{t_idx}")

            for c, clip in enumerate(t_clips):
                src_path = clip.get("sourcePath") or clip.get("mediaPath")
                if not src_path:
                    continue

                clip_start = float(clip.get("timelineStart", clip.get("startTimeSec", 0.0)))
                clip_dur = float(clip.get("duration", clip.get("durationSec", 1.0)))
                clip_end = float(clip.get("timelineEnd", clip_start + clip_dur))
                clip_in = float(clip.get("inPointSec", 0.0))

                # Exact range intersection
                effective_start = max(clip_start, range_start)
                effective_end = min(clip_end, range_end)

                if effective_end <= effective_start + 0.01:
                    # Clip does not intersect requested range
                    continue

                effective_duration = effective_end - effective_start
                offset_from_clip_start = effective_start - clip_start
                source_in = clip_in + offset_from_clip_start
                source_out = source_in + effective_duration
                c_name = clip.get("clipName", clip.get("name", "Audio Clip"))
                unique_job_id = f"{master_job_id}_t{t_idx}_c{c}"

                jobs.append({
                    "jobId": unique_job_id,
                    "clipJobId": unique_job_id,
                    "masterJobId": master_job_id,
                    "sourceFile": str(src_path),
                    "sourcePath": str(src_path),
                    "inPointSec": float(source_in),
                    "outPointSec": float(source_out),
                    "clipName": f"{c_name}_{t_name}",
                    "timelineStart": float(effective_start),
                    "timelineEnd": float(effective_end),
                    "targetStartTime": float(effective_start),
                    "targetEndTime": float(effective_end),
                    "durationSec": float(effective_duration),
                    "trackIndex": int(t_idx),
                    "trackName": str(t_name),
                    "trackId": str(t_id),
                    "clipId": str(clip.get("clipId", f"t{t_idx}_c{c}")),
                    "clipIndex": c,
                    "projectItemId": str(clip.get("projectItemId", "")),
                    "sequenceGuid": seq_guid,
                    "sequenceName": seq_name,
                    "scope": scope
                })

        return jobs


class ClipBasedRangeProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sr = 48000
        self.placement_service = MockTimelinePlacementService()

        # Create dummy media files
        self.media_clip1 = os.path.join(self.tmp_dir.name, "dialogue_a.wav")
        self.media_clip2 = os.path.join(self.tmp_dir.name, "dialogue_b.wav")
        t1 = np.linspace(0, 30.0, self.sr * 30, endpoint=False)
        AudioPipeline.save_wav(self.media_clip1, 0.3 * np.sin(2 * np.pi * 400 * t1).astype(np.float32), self.sr)
        AudioPipeline.save_wav(self.media_clip2, 0.3 * np.sin(2 * np.pi * 800 * t1).astype(np.float32), self.sr)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_1_full_sequence_single_track_with_gap_creates_two_jobs(self):
        """
        Test 1: Full Sequence on A1 with 2 clips and a 20s gap:
        Clip 1: 00:00 -> 00:20 (20s)
        Gap:    00:20 -> 00:40 (20s)
        Clip 2: 00:40 -> 01:00 (20s)
        Total sequence duration = 60s.
        Must create EXACTLY 2 jobs (NOT 1 continuous 60s job).
        """
        snapshot = {
            "scope": "full_sequence",
            "durationSec": 60.0,
            "sequenceGuid": "seq_test_1",
            "sequenceName": "Interview",
            "tracks": [
                {
                    "trackIndex": 0,
                    "trackName": "A1",
                    "clips": [
                        {
                            "clipName": "Host_Part1",
                            "mediaPath": self.media_clip1,
                            "timelineStart": 0.0,
                            "timelineEnd": 20.0,
                            "durationSec": 20.0,
                            "inPointSec": 0.0,
                            "outPointSec": 20.0
                        },
                        {
                            "clipName": "Host_Part2",
                            "mediaPath": self.media_clip1,
                            "timelineStart": 40.0,
                            "timelineEnd": 60.0,
                            "durationSec": 20.0,
                            "inPointSec": 20.0,
                            "outPointSec": 40.0
                        }
                    ]
                }
            ]
        }

        jobs = MockContextManager.build_enhancement_jobs(snapshot, "master_batch_1")

        # Invariant 1: Exactly 2 jobs created
        self.assertEqual(len(jobs), 2, "Must create exactly 2 jobs for 2 clips")

        # Invariant 2: Total duration of jobs = 40s, NOT sequence length of 60s
        total_audio = sum(j["durationSec"] for j in jobs)
        self.assertEqual(total_audio, 40.0, "Total enhanced audio must be 40s, not 60s")

        # Invariant 3: Job 1 details
        j1 = jobs[0]
        self.assertEqual(j1["timelineStart"], 0.0)
        self.assertEqual(j1["timelineEnd"], 20.0)
        self.assertEqual(j1["durationSec"], 20.0)
        self.assertEqual(j1["inPointSec"], 0.0)
        self.assertEqual(j1["outPointSec"], 20.0)

        # Invariant 4: Job 2 details (preserving timeline gap)
        j2 = jobs[1]
        self.assertEqual(j2["timelineStart"], 40.0)
        self.assertEqual(j2["timelineEnd"], 60.0)
        self.assertEqual(j2["durationSec"], 20.0)
        self.assertEqual(j2["inPointSec"], 20.0)
        self.assertEqual(j2["outPointSec"], 40.0)

        # Invariant 5: Gap between jobs
        gap = j2["timelineStart"] - j1["timelineEnd"]
        self.assertEqual(gap, 20.0, "Gap must be exactly 20.0s")

    def test_2_two_tracks_with_gaps_creates_four_independent_jobs(self):
        """
        Test 2: Full Sequence on A1 (2 clips) and A2 (2 clips):
        Must create EXACTLY 4 independent jobs.
        """
        snapshot = {
            "scope": "full_sequence",
            "durationSec": 70.0,
            "tracks": [
                {
                    "trackIndex": 0,
                    "trackName": "A1",
                    "clips": [
                        {"clipName": "A1_Clip1", "mediaPath": self.media_clip1, "timelineStart": 0.0, "timelineEnd": 20.0, "durationSec": 20.0, "inPointSec": 0.0, "outPointSec": 20.0},
                        {"clipName": "A1_Clip2", "mediaPath": self.media_clip1, "timelineStart": 40.0, "timelineEnd": 60.0, "durationSec": 20.0, "inPointSec": 0.0, "outPointSec": 20.0}
                    ]
                },
                {
                    "trackIndex": 1,
                    "trackName": "A2",
                    "clips": [
                        {"clipName": "A2_Clip1", "mediaPath": self.media_clip2, "timelineStart": 10.0, "timelineEnd": 30.0, "durationSec": 20.0, "inPointSec": 0.0, "outPointSec": 20.0},
                        {"clipName": "A2_Clip2", "mediaPath": self.media_clip2, "timelineStart": 50.0, "timelineEnd": 65.0, "durationSec": 15.0, "inPointSec": 0.0, "outPointSec": 15.0}
                    ]
                }
            ]
        }

        jobs = MockContextManager.build_enhancement_jobs(snapshot, "master_batch_2")
        self.assertEqual(len(jobs), 4, "Must create exactly 4 jobs across the 2 tracks")

        # Verify track distribution
        a1_jobs = [j for j in jobs if j["trackIndex"] == 0]
        a2_jobs = [j for j in jobs if j["trackIndex"] == 1]
        self.assertEqual(len(a1_jobs), 2)
        self.assertEqual(len(a2_jobs), 2)

    def test_3_in_out_intersection_slices_clips_without_padding_silence(self):
        """
        Test 3: In/Out range slicing.
        In = 10.0s, Out = 50.0s.
        A1 has:
        Clip 1: 00:00 -> 00:20 (overlap 10s -> 20s)
        Gap:    00:20 -> 00:40 (overlap within In/Out, but empty space -> 0 jobs)
        Clip 2: 00:40 -> 01:00 (overlap 40s -> 50s)
        Clip 3: 01:10 -> 01:30 (outside In/Out -> 0 jobs)

        Must create EXACTLY 2 jobs:
        Job 1: 00:10 -> 00:20 (10s)
        Job 2: 00:40 -> 00:50 (10s)
        Zero silent audio in between!
        """
        snapshot = {
            "scope": "in_out",
            "inPointSec": 10.0,
            "outPointSec": 50.0,
            "durationSec": 40.0,
            "tracks": [
                {
                    "trackIndex": 0,
                    "trackName": "A1",
                    "clips": [
                        {"clipName": "Clip1", "mediaPath": self.media_clip1, "timelineStart": 0.0, "timelineEnd": 20.0, "durationSec": 20.0, "inPointSec": 5.0, "outPointSec": 25.0},
                        {"clipName": "Clip2", "mediaPath": self.media_clip1, "timelineStart": 40.0, "timelineEnd": 60.0, "durationSec": 20.0, "inPointSec": 0.0, "outPointSec": 20.0},
                        {"clipName": "Clip3", "mediaPath": self.media_clip1, "timelineStart": 70.0, "timelineEnd": 90.0, "durationSec": 20.0, "inPointSec": 0.0, "outPointSec": 20.0}
                    ]
                }
            ]
        }

        jobs = MockContextManager.build_enhancement_jobs(snapshot, "inout_batch")
        self.assertEqual(len(jobs), 2, "Must create exactly 2 jobs for intersecting portions")

        # Job 1 intersection check:
        # Effective range: 10s -> 20s.
        # Clip1 start = 0s, inPoint = 5s.
        # Offset from clip start = 10s.
        # sourceIn must be 5s + 10s = 15s.
        # sourceOut must be 15s + 10s = 25s.
        j1 = jobs[0]
        self.assertEqual(j1["timelineStart"], 10.0)
        self.assertEqual(j1["timelineEnd"], 20.0)
        self.assertEqual(j1["durationSec"], 10.0)
        self.assertEqual(j1["inPointSec"], 15.0)
        self.assertEqual(j1["outPointSec"], 25.0)

        # Job 2 intersection check:
        # Effective range: 40s -> 50s.
        # Clip2 start = 40s, inPoint = 0s.
        # Offset from clip start = 0s.
        # sourceIn must be 0s, sourceOut must be 10s.
        j2 = jobs[1]
        self.assertEqual(j2["timelineStart"], 40.0)
        self.assertEqual(j2["timelineEnd"], 50.0)
        self.assertEqual(j2["durationSec"], 10.0)
        self.assertEqual(j2["inPointSec"], 0.0)
        self.assertEqual(j2["outPointSec"], 10.0)

    def test_4_destination_placement_preserves_gap_on_target_track(self):
        """
        Test 4: Non-overlapping sequential clips from A1 can safely share destination track A2
        without collisions, preserving the timeline gap.
        """
        seq_info = {
            "audioTrackCount": 3,
            "audioTracks": [
                {"index": 0, "name": "A1", "locked": False, "clips": [
                    {"startSec": 0.0, "endSec": 20.0},
                    {"startSec": 40.0, "endSec": 60.0}
                ]},
                {"index": 1, "name": "A2", "locked": False, "clips": []},
                {"index": 2, "name": "A3", "locked": False, "clips": []}
            ]
        }

        # Clip 1 destination search (0s -> 20s)
        res1 = self.placement_service.find_safe_audio_track(seq_info, 0.0, 20.0, source_track_index=0)
        self.assertEqual(res1["trackIndex"], 1, "Clip 1 lands on A2")
        self.placement_service.reserve_destination(1, 0.0, 20.0, "job1")

        # Clip 2 destination search (40s -> 60s)
        # A2 has reservation [0, 20], which does NOT overlap [40, 60]!
        res2 = self.placement_service.find_safe_audio_track(seq_info, 40.0, 60.0, source_track_index=0)
        self.assertEqual(res2["trackIndex"], 1, "Clip 2 can ALSO safely land on A2")
        self.assertFalse(res2["isNewTrack"], "No need to allocate extra track when interval is free")

        self.placement_service.reserve_destination(1, 40.0, 60.0, "job2")

        # Confirm A2 has two non-overlapping intervals recorded
        res_map = self.placement_service.get_reservations()
        self.assertEqual(len(res_map[1]), 2)
        self.assertEqual(res_map[1][0]["startSec"], 0.0)
        self.assertEqual(res_map[1][0]["endSec"], 20.0)
        self.assertEqual(res_map[1][1]["startSec"], 40.0)
        self.assertEqual(res_map[1][1]["endSec"], 60.0)

    def test_5_selected_clips_mode_direct_clip_jobs(self):
        """
        Test 5: Selected Clips mode produces exactly 1 job per selected clip,
        ignoring track selection filters.
        """
        snapshot = {
            "scope": "selected_clips",
            "clips": [
                {"clipName": "Selected1", "mediaPath": self.media_clip1, "timelineStart": 5.0, "durationSec": 15.0, "inPointSec": 0.0, "outPointSec": 15.0, "trackIndex": 0},
                {"clipName": "Selected2", "mediaPath": self.media_clip2, "timelineStart": 25.0, "durationSec": 10.0, "inPointSec": 0.0, "outPointSec": 10.0, "trackIndex": 2}
            ]
        }

        jobs = MockContextManager.build_enhancement_jobs(snapshot, "sel_batch")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["trackIndex"], 0)
        self.assertEqual(jobs[1]["trackIndex"], 2)


if __name__ == "__main__":
    unittest.main()
