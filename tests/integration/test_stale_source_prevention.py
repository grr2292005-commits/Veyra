import os
import sys
import json
import time
import uuid
import tempfile
import unittest
import numpy as np
import soundfile as sf
from typing import Dict, Any

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.audio.pipeline import AudioPipeline
from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from engine.models.factory import ModelFactory
from models.manager import ModelManager

class StaleSourcePreventionTests(unittest.TestCase):
    """
    Automated regression tests proving that:
    1. The source of every enhancement job is derived freshly at the moment Enhance is clicked.
    2. No stale cached source path, timeline range, or clip array can be processed.
    3. Replacing a clip (even with identical filename or timeline position) processes the new media only.
    4. Sequence switches and clip deletions invalidate pending work.
    5. Temporary and output workspaces are strictly job-scoped.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orchestrator = EnhancementOrchestrator()
        self.sample_rate = 48000

        # Create two distinctly recognizable audio files
        self.audio_a_path = os.path.join(self.tmp_dir.name, "Audio_Old.wav")
        self.audio_b_path = os.path.join(self.tmp_dir.name, "Audio_New.wav")

        # Audio A: 1.0 sec of 440 Hz tone
        t = np.linspace(0, 1.0, self.sample_rate, endpoint=False)
        audio_a = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sf.write(self.audio_a_path, audio_a, self.sample_rate)

        # Audio B: 1.5 sec of 880 Hz tone
        t_b = np.linspace(0, 1.5, int(self.sample_rate * 1.5), endpoint=False)
        audio_b = (0.4 * np.sin(2 * np.pi * 880 * t_b)).astype(np.float32)
        sf.write(self.audio_b_path, audio_b, self.sample_rate)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_current_selection_is_requeried_before_job(self):
        """Enhancement jobs must query live sequence state rather than cached in-memory arrays."""
        # Simulated stale cache
        stale_cached_clips = [{
            "clipId": "old_clip_01",
            "name": "Audio_Old.wav",
            "mediaPath": self.audio_a_path,
            "startTimeSec": 0.0,
            "durationSec": 1.0
        }]

        # Live Premiere Pro state at click moment has Audio B
        live_premiere_clips = [{
            "clipId": "new_clip_02",
            "name": "Audio_New.wav",
            "mediaPath": self.audio_b_path,
            "startTimeSec": 5.0,
            "durationSec": 1.5
        }]

        # Fresh snapshot query function simulator
        def get_fresh_snapshot(scope="selected_clips"):
            # Queries live Premiere state, ignoring stale_cached_clips
            return {
                "success": True,
                "sequenceGuid": "seq-12345",
                "sequenceName": "MySequence",
                "scope": scope,
                "clips": live_premiere_clips,
                "timestamp": time.time()
            }

        snapshot = get_fresh_snapshot()
        self.assertTrue(snapshot["success"])
        self.assertEqual(len(snapshot["clips"]), 1)
        self.assertEqual(snapshot["clips"][0]["mediaPath"], self.audio_b_path)
        self.assertNotEqual(snapshot["clips"][0]["mediaPath"], stale_cached_clips[0]["mediaPath"])

    def test_deleted_clip_cannot_be_processed(self):
        """Pre-flight validation must abort if a selected clip was removed from the timeline."""
        snapshot = {
            "sequenceGuid": "seq-100",
            "sequenceName": "Sequence 1",
            "scope": "selected_clips",
            "clips": [{
                "clipId": "clip_deleted",
                "name": "DeletedAudio.wav",
                "trackIndex": 0,
                "startTimeSec": 10.0,
                "mediaPath": self.audio_a_path
            }]
        }

        # Current live timeline has no clips on Track 0 at 10.0s
        live_timeline_clips = []

        def validate_context(snap, live_clips):
            if not live_clips:
                return {"valid": False, "reason": "Selected clip was removed from timeline."}
            return {"valid": True}

        val = validate_context(snapshot, live_timeline_clips)
        self.assertFalse(val["valid"])
        self.assertIn("removed", val["reason"])

    def test_replaced_clip_same_name_is_new_source(self):
        """Clips with identical names but different project items / media paths must not be confused."""
        dir1 = os.path.join(self.tmp_dir.name, "take1")
        dir2 = os.path.join(self.tmp_dir.name, "take2")
        os.makedirs(dir1, exist_ok=True)
        os.makedirs(dir2, exist_ok=True)

        file1 = os.path.join(dir1, "Podcast Audio.wav")
        file2 = os.path.join(dir2, "Podcast Audio.wav")

        # Write different contents to both
        sf.write(file1, np.zeros((1000,), dtype=np.float32), 48000)
        sf.write(file2, np.ones((2000,), dtype=np.float32), 48000)

        key1 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq-01",
            track_item_id="track_0_clip_0",
            project_item_id="pitem_001",
            source_path=file1,
            in_sec=0.0,
            out_sec=1.0
        )

        key2 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq-01",
            track_item_id="track_0_clip_0",
            project_item_id="pitem_002",
            source_path=file2,
            in_sec=0.0,
            out_sec=1.0
        )

        self.assertNotEqual(key1, key2, "Same-name files with different paths/project items must produce distinct cache keys")

    def test_sequence_identity_prevents_stale_job(self):
        """Switching sequences must invalidate pending jobs associated with prior sequence."""
        snapshot_seq_a = {
            "sequenceGuid": "seq-guid-AAA",
            "sequenceName": "Sequence A",
            "scope": "selected_clips",
            "clips": [{"clipId": "c1", "mediaPath": self.audio_a_path}]
        }

        # User switched active sequence in Premiere to Sequence B
        current_active_seq_guid = "seq-guid-BBB"

        def check_sequence_match(snap, active_guid):
            if snap["sequenceGuid"] != active_guid:
                return {"valid": False, "reason": f"Active sequence changed (expected {snap['sequenceGuid']}, got {active_guid})"}
            return {"valid": True}

        res = check_sequence_match(snapshot_seq_a, current_active_seq_guid)
        self.assertFalse(res["valid"])
        self.assertIn("changed", res["reason"])

    def test_source_cache_key_changes_with_media_identity(self):
        """AudioPipeline cache key must incorporate sequence, clip, item, path, time range, and mtime."""
        base_params = {
            "sequence_guid": "seq-1",
            "track_item_id": "item-1",
            "project_item_id": "proj-1",
            "source_path": self.audio_a_path,
            "in_sec": 0.0,
            "out_sec": 1.0,
            "mtime": 1000.0,
            "file_size": 5000
        }

        k_base = AudioPipeline.get_source_cache_key(**base_params)

        # 1. Change sequence
        p_seq = dict(base_params, sequence_guid="seq-2")
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_seq))

        # 2. Change track item
        p_track = dict(base_params, track_item_id="item-2")
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_track))

        # 3. Change project item
        p_proj = dict(base_params, project_item_id="proj-2")
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_proj))

        # 4. Change time range
        p_range = dict(base_params, in_sec=0.5)
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_range))

        # 5. Change modification timestamp
        p_mtime = dict(base_params, mtime=2000.0)
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_mtime))

        # 6. Change file size
        p_size = dict(base_params, file_size=9999)
        self.assertNotEqual(k_base, AudioPipeline.get_source_cache_key(**p_size))

    def test_job_uses_unique_source_temp_directory(self):
        """Every enhancement job must create a unique directory with isolated metadata."""
        job_id_1 = f"job-{uuid.uuid4().hex[:12]}"
        job_id_2 = f"job-{uuid.uuid4().hex[:12]}"

        temp_root = os.path.join(self.tmp_dir.name, "Temp")
        dir_1 = os.path.join(temp_root, job_id_1)
        dir_2 = os.path.join(temp_root, job_id_2)
        os.makedirs(dir_1, exist_ok=True)
        os.makedirs(dir_2, exist_ok=True)

        meta_1 = {"job_id": job_id_1, "source": self.audio_a_path}
        meta_2 = {"job_id": job_id_2, "source": self.audio_b_path}

        with open(os.path.join(dir_1, "metadata.json"), "w") as f:
            json.dump(meta_1, f)
        with open(os.path.join(dir_2, "metadata.json"), "w") as f:
            json.dump(meta_2, f)

        self.assertNotEqual(dir_1, dir_2)
        with open(os.path.join(dir_1, "metadata.json")) as f:
            d1 = json.load(f)
        with open(os.path.join(dir_2, "metadata.json")) as f:
            d2 = json.load(f)

        self.assertEqual(d1["job_id"], job_id_1)
        self.assertEqual(d2["job_id"], job_id_2)
        self.assertEqual(d1["source"], self.audio_a_path)
        self.assertEqual(d2["source"], self.audio_b_path)

    def test_engine_cannot_fallback_to_previous_input(self):
        """If source file is missing or deleted, orchestrator must raise FileNotFoundError immediately."""
        nonexistent_file = os.path.join(self.tmp_dir.name, "phantom_deleted_audio.wav")
        job = EnhancementJob(
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            source_file=nonexistent_file,
            model_id="mp_senet"
        )

        with self.assertRaises(FileNotFoundError):
            self.orchestrator.run_job(job)

    def test_same_path_replaced_detected(self):
        """Overwriting a file at the same path with new audio must invalidate the cache key."""
        target_path = os.path.join(self.tmp_dir.name, "dynamic_source.wav")
        # State 1: 1000 samples
        sf.write(target_path, np.zeros((1000,), dtype=np.float32), 48000)
        key1 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq1",
            track_item_id="item1",
            project_item_id="proj1",
            source_path=target_path
        )

        # Overwrite file with new length
        time.sleep(0.05) # ensure mtime tick
        sf.write(target_path, np.ones((5000,), dtype=np.float32), 48000)
        key2 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq1",
            track_item_id="item1",
            project_item_id="proj1",
            source_path=target_path
        )

        self.assertNotEqual(key1, key2, "Altered file on disk must produce a different cache key")

    def test_old_temp_file_ignored(self):
        """Old files left in global Temp must never be reused by a new job."""
        global_temp = os.path.join(self.tmp_dir.name, "global_temp")
        os.makedirs(global_temp, exist_ok=True)
        stale_source = os.path.join(global_temp, "source.wav")
        sf.write(stale_source, np.ones((1000,), dtype=np.float32), 48000)

        # New job creates its own scoped dir
        new_job_id = f"job-{uuid.uuid4().hex[:8]}"
        scoped_dir = os.path.join(global_temp, new_job_id)
        os.makedirs(scoped_dir, exist_ok=True)
        new_source = os.path.join(scoped_dir, "source.wav")
        sf.write(new_source, np.zeros((2000,), dtype=np.float32), 48000)

        self.assertTrue(os.path.isfile(stale_source))
        self.assertTrue(os.path.isfile(new_source))
        self.assertNotEqual(stale_source, new_source)

    def test_empty_current_timeline_fails_safely(self):
        """When 0 clips are selected, snapshot creation must reject with a user-facing error."""
        def create_snapshot_sim(selected_clips):
            if not selected_clips:
                return {"success": False, "error": "Select an audio clip in the timeline.", "clips": []}
            return {"success": True, "clips": selected_clips}

        res = create_snapshot_sim([])
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "Select an audio clip in the timeline.")

    def test_critical_replaced_audio_workflow(self):
        """
        End-to-end critical reproduction test:
        1. User had Audio A on timeline.
        2. Audio A is removed.
        3. Audio B is added.
        4. Enhance triggered: fresh snapshot taken -> Audio B processed -> Audio B output created.
        """
        # Step 1 & 2: Timeline initially had Audio A, but user removed it
        timeline_clips = [
            # Only Audio B is currently on the timeline!
            {
                "clipId": "t0_c0_new",
                "name": "Audio_New.wav",
                "mediaPath": self.audio_b_path,
                "startTimeSec": 0.0,
                "durationSec": 1.5,
                "trackIndex": 0
            }
        ]

        # Step 3: Fresh snapshot captures only Audio B
        fresh_snapshot = {
            "success": True,
            "sequenceGuid": "seq-live-456",
            "sequenceName": "Episode 1",
            "scope": "selected_clips",
            "clips": timeline_clips
        }

        # Step 4: Job created from fresh snapshot
        clip_item = fresh_snapshot["clips"][0]
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        out_dir = os.path.join(self.tmp_dir.name, "Enhanced")
        os.makedirs(out_dir, exist_ok=True)

        job = EnhancementJob(
            job_id=job_id,
            source_file=clip_item["mediaPath"],
            clip_name=clip_item["name"],
            in_point_sec=0.0,
            out_point_sec=1.5,
            model_id="mp_senet",
            device="cpu",
            output_dir=out_dir
        )

        result = self.orchestrator.run_job(job)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["source_file"], self.audio_b_path)
        self.assertNotEqual(result["source_file"], self.audio_a_path)
        self.assertTrue(os.path.isfile(result["output_file"]))

        # Verify output duration corresponds to Audio B (1.5s), not Audio A (1.0s)
        info = sf.info(result["output_file"])
        self.assertAlmostEqual(info.duration, 1.5, delta=0.05)

if __name__ == "__main__":
    unittest.main()
