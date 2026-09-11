import os
import sys
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class TrackSelectionModel:
    """
    Python simulation of Speechify's Scope and Track Selection architecture.
    Reflects the exact 3-scope model:
    - selected_clips: uses selected clips directly, NO track filtering.
    - in_out: requires audio track selection + In/Out range.
    - full_sequence: requires audio track selection.
    """
    VALID_SCOPES = ["selected_clips", "in_out", "full_sequence"]

    def __init__(self):
        self.scope = "selected_clips"
        self.tracks = []
        self.active_sequence_id = None
        self.saved_track_prefs = {} # seq_id -> { track_id: bool }

    def set_scope(self, new_scope: str):
        if new_scope not in self.VALID_SCOPES:
            raise ValueError(f"Invalid processing scope '{new_scope}'. Allowed scopes: {self.VALID_SCOPES}")
        self.scope = new_scope

    def update_tracks_for_sequence(self, seq_id: str, audio_tracks: list):
        if seq_id != self.active_sequence_id:
            self.active_sequence_id = seq_id

        existing_prefs = self.saved_track_prefs.get(seq_id, {})
        new_tracks = []
        for i, t in enumerate(audio_tracks):
            name = t.get("name") if isinstance(t, dict) else str(t)
            default_name = name or (f"Audio {i+1}")
            # Stable track identity by index preserves user selection across renaming
            track_id = f"audio_track_{i}"
            enabled = existing_prefs.get(track_id, (i == 0))
            display_label = f"A{i+1} · {default_name}" if default_name != f"Audio {i+1}" else f"A{i+1} · Audio {i+1}"
            new_tracks.append({
                "id": track_id,
                "index": i,
                "name": default_name,
                "type": "audio",
                "enabled": enabled,
                "display_label": display_label
            })
        self.tracks = new_tracks
        return self.tracks

    def toggle_track(self, track_id: str):
        for t in self.tracks:
            if t["id"] == track_id:
                t["enabled"] = not t["enabled"]
                if self.active_sequence_id:
                    if self.active_sequence_id not in self.saved_track_prefs:
                        self.saved_track_prefs[self.active_sequence_id] = {}
                    self.saved_track_prefs[self.active_sequence_id][track_id] = t["enabled"]
                break

    def get_selected_count(self) -> int:
        return len([t for t in self.tracks if t["enabled"]])

    def get_selected_track_indices(self) -> set:
        return {t["index"] for t in self.tracks if t["enabled"]}

    def get_summary_text(self) -> str:
        count = self.get_selected_count()
        total = len(self.tracks)
        if count == 0:
            return "Select audio tracks"
        if total > 0 and count == total:
            return "All audio tracks"
        if count == 1:
            return "1 track selected"
        return f"{count} tracks selected"

    def filter_clips_for_job(self, clips: list, in_sec: float = 0.0, out_sec: float = 1000.0) -> list:
        """
        Filters clips based on the active scope:
        - Selected Clips: returns clips directly, ignoring any track filter.
        - In/Out: returns clips intersecting time range on selected tracks.
        - Full Sequence: returns clips on selected tracks.
        """
        if self.scope == "selected_clips":
            return list(clips) # No track filtering!

        selected_indices = self.get_selected_track_indices()
        filtered = []
        for c in clips:
            track_idx = c.get("trackIndex", c.get("track_index", 0))
            if track_idx not in selected_indices:
                continue
            start = c.get("startTimeSec", c.get("start_time_sec", 0.0))
            dur = c.get("durationSec", c.get("duration_sec", 0.0))
            if (start + dur > in_sec) and (start < out_sec):
                filtered.append(c)
        return filtered

    def validate_job(self, selected_clips: list, in_dur: float = 0.0) -> tuple:
        """Returns (is_valid: bool, error_message: str)"""
        if self.scope == "selected_clips":
            if not selected_clips:
                return False, "Select an audio clip in the timeline."
            return True, ""
        elif self.scope == "in_out":
            if in_dur <= 0:
                return False, "Set an In/Out range."
            if self.get_selected_count() == 0:
                return False, "Select at least one audio track."
            return True, ""
        elif self.scope == "full_sequence":
            if self.get_selected_count() == 0:
                return False, "Select at least one audio track."
            return True, ""
        return False, "Unknown scope"


class TrackSelectionUnitTests(unittest.TestCase):
    def setUp(self):
        self.model = TrackSelectionModel()

    def test_scope_has_exactly_three_modes(self):
        """The UI and data model must contain exactly: Selected Clips, In / Out, Full Sequence."""
        self.assertEqual(len(TrackSelectionModel.VALID_SCOPES), 3)
        self.assertIn("selected_clips", TrackSelectionModel.VALID_SCOPES)
        self.assertIn("in_out", TrackSelectionModel.VALID_SCOPES)
        self.assertIn("full_sequence", TrackSelectionModel.VALID_SCOPES)
        # Verify 'tracks' is NOT a processing scope
        self.assertNotIn("tracks", TrackSelectionModel.VALID_SCOPES)

        with self.assertRaises(ValueError):
            self.model.set_scope("tracks")

    def test_zero_tracks(self):
        """Zero tracks in sequence: handles empty list cleanly without errors."""
        tracks = self.model.update_tracks_for_sequence("seq_empty", [])
        self.assertEqual(len(tracks), 0)
        self.assertEqual(self.model.get_selected_count(), 0)
        self.assertEqual(self.model.get_summary_text(), "Select audio tracks")

    def test_single_track(self):
        """One track in sequence: properly formats A1 · Dialogue and defaults enabled."""
        tracks = self.model.update_tracks_for_sequence("seq_single", [{"name": "Dialogue"}])
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["display_label"], "A1 · Dialogue")
        self.assertTrue(tracks[0]["enabled"])
        self.assertEqual(self.model.get_selected_count(), 1)
        self.assertEqual(self.model.get_summary_text(), "All audio tracks")

    def test_multiple_tracks(self):
        """Multiple tracks: A1 Dialogue, A2 Music, A3 Commentary, A4 SFX."""
        tracks = self.model.update_tracks_for_sequence("seq_multi", [
            {"name": "Dialogue"},
            {"name": "Music"},
            {"name": "Commentary"},
            {"name": "SFX"}
        ])
        self.assertEqual(len(tracks), 4)
        self.assertEqual(tracks[0]["display_label"], "A1 · Dialogue")
        self.assertEqual(tracks[1]["display_label"], "A2 · Music")
        self.assertEqual(tracks[2]["display_label"], "A3 · Commentary")
        self.assertEqual(tracks[3]["display_label"], "A4 · SFX")

        # Toggle track 2 (Commentary) on
        self.model.toggle_track(tracks[2]["id"])
        self.assertEqual(self.model.get_selected_count(), 2) # A1 and A3
        self.assertEqual(self.model.get_summary_text(), "2 tracks selected")

    def test_duplicate_track_names(self):
        """Duplicate track names (e.g. Dialogue on A1 and Dialogue on A2) have unique IDs."""
        tracks = self.model.update_tracks_for_sequence("seq_dup", [
            {"name": "Dialogue"},
            {"name": "Dialogue"}
        ])
        self.assertEqual(len(tracks), 2)
        self.assertNotEqual(tracks[0]["id"], tracks[1]["id"])

    def test_renamed_tracks(self):
        """When user renames a track in sequence, the name updates while identity/selection is preserved."""
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Audio 1"}])
        # Renamed to Voiceover
        tracks = self.model.update_tracks_for_sequence("seq_1", [{"name": "Voiceover"}])
        self.assertEqual(tracks[0]["display_label"], "A1 · Voiceover")
        self.assertEqual(tracks[0]["index"], 0)
        self.assertTrue(tracks[0]["enabled"])

    def test_removed_tracks(self):
        """When track count shrinks, removed tracks are safely excluded."""
        self.model.update_tracks_for_sequence("seq_shrink", [{"name": "A1"}, {"name": "A2"}, {"name": "A3"}])
        self.assertEqual(len(self.model.tracks), 3)

        # Removed A3
        tracks = self.model.update_tracks_for_sequence("seq_shrink", [{"name": "A1"}, {"name": "A2"}])
        self.assertEqual(len(tracks), 2)

    def test_sequence_switching_prevents_stale_track_application(self):
        """Switching to a new sequence revalidates and never applies stale selection across sequences."""
        self.model.update_tracks_for_sequence("seq_1", [{"name": "A1"}, {"name": "A2"}, {"name": "A3"}, {"name": "A4"}])
        track4_id = self.model.tracks[3]["id"]
        self.model.toggle_track(track4_id)

        tracks_seq2 = self.model.update_tracks_for_sequence("seq_2", [{"name": "Music 1"}, {"name": "Music 2"}])
        self.assertEqual(len(tracks_seq2), 2)
        self.assertEqual(self.model.get_selected_count(), 1) # Only default A1 for fresh seq_2

    def test_selected_clips_have_no_track_filter(self):
        """Selected Clips mode must process selected clips regardless of track filter."""
        self.model.set_scope("selected_clips")
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Dialogue"}, {"name": "Music"}])
        # Uncheck all tracks
        self.model.toggle_track("audio_track_0")
        self.assertEqual(self.model.get_selected_count(), 0)

        clips = [
            {"mediaPath": "fileA.wav", "trackIndex": 1, "startTimeSec": 0, "durationSec": 5},
            {"mediaPath": "fileB.wav", "trackIndex": 0, "startTimeSec": 10, "durationSec": 5}
        ]
        # Must return all clips despite zero tracks selected
        res = self.model.filter_clips_for_job(clips)
        self.assertEqual(len(res), 2)

        valid, err = self.model.validate_job(clips)
        self.assertTrue(valid)
        self.assertEqual(err, "")

    def test_in_out_requires_track_selection(self):
        """In/Out mode requires at least one track and valid In/Out duration."""
        self.model.set_scope("in_out")
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Dialogue"}])

        # Test duration 0 error
        valid, err = self.model.validate_job([], in_dur=0.0)
        self.assertFalse(valid)
        self.assertEqual(err, "Set an In/Out range.")

        # Test zero tracks selected
        self.model.toggle_track("audio_track_0") # disable track 0
        valid, err = self.model.validate_job([], in_dur=15.0)
        self.assertFalse(valid)
        self.assertEqual(err, "Select at least one audio track.")

    def test_full_sequence_requires_track_selection(self):
        """Full Sequence mode requires at least one track selected."""
        self.model.set_scope("full_sequence")
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Dialogue"}])

        valid, err = self.model.validate_job([])
        self.assertTrue(valid)

        self.model.toggle_track("audio_track_0") # disable
        valid, err = self.model.validate_job([])
        self.assertFalse(valid)
        self.assertEqual(err, "Select at least one audio track.")

    def test_track_selection_not_applied_to_selected_clips(self):
        """Track preferences configured in In/Out must never leak into Selected Clips mode."""
        self.model.set_scope("in_out")
        self.model.update_tracks_for_sequence("seq_1", [{"name": "A1"}, {"name": "A2"}, {"name": "A3"}])
        # In In/Out mode, user selected only A1
        clips = [
            {"mediaPath": "clip_on_A2.wav", "trackIndex": 1, "startTimeSec": 0, "durationSec": 10}
        ]
        # In In/Out mode, clip on A2 is excluded
        self.assertEqual(len(self.model.filter_clips_for_job(clips, 0, 20)), 0)

        # Switch to Selected Clips
        self.model.set_scope("selected_clips")
        # Same clip on A2 must now be processed
        res = self.model.filter_clips_for_job(clips)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["mediaPath"], "clip_on_A2.wav")

    def test_track_selection_per_sequence(self):
        """Track selections must be preserved independently per sequence."""
        # Seq A: Select track 0 only
        self.model.update_tracks_for_sequence("seq_A", [{"name": "A1"}, {"name": "A2"}])
        self.assertEqual(self.model.get_selected_count(), 1)

        # Seq B: Select track 1
        self.model.update_tracks_for_sequence("seq_B", [{"name": "B1"}, {"name": "B2"}])
        self.model.toggle_track("audio_track_0") # uncheck B1
        self.model.toggle_track("audio_track_1") # check B2
        self.assertEqual(self.model.get_selected_track_indices(), {1})

        # Switch back to Seq A: track 0 must still be selected
        self.model.update_tracks_for_sequence("seq_A", [{"name": "A1"}, {"name": "A2"}])
        self.assertEqual(self.model.get_selected_track_indices(), {0})

    def test_track_rename_preserves_identity(self):
        """Renaming a track must preserve user selection state."""
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Dialogue"}, {"name": "Music"}])
        self.model.toggle_track("audio_track_1") # Enable Music
        self.assertEqual(self.model.get_selected_track_indices(), {0, 1})

        # Rename Dialogue to Lead Vocal
        self.model.update_tracks_for_sequence("seq_1", [{"name": "Lead Vocal"}, {"name": "Music"}])
        self.assertEqual(self.model.get_selected_track_indices(), {0, 1})
        self.assertEqual(self.model.tracks[0]["display_label"], "A1 · Lead Vocal")

    def test_track_removal_cleans_selection(self):
        """When tracks are deleted in Premiere, selections are cleaned up."""
        self.model.update_tracks_for_sequence("seq_1", [{"name": "A1"}, {"name": "A2"}, {"name": "A3"}, {"name": "A4"}])
        self.model.toggle_track("audio_track_3") # Enable track 3 (A4)
        self.assertEqual(self.model.get_selected_count(), 2) # A1 and A4

        # Timeline trimmed to 2 tracks
        self.model.update_tracks_for_sequence("seq_1", [{"name": "A1"}, {"name": "A2"}])
        self.assertEqual(len(self.model.tracks), 2)
        self.assertEqual(self.model.get_selected_track_indices(), {0})

    def test_many_audio_tracks(self):
        """Verify performance and formatting with 2, 4, 8, 16, 32 audio tracks."""
        for count in [2, 4, 8, 16, 32]:
            track_defs = [{"name": f"Track {i+1}"} for i in range(count)]
            tracks = self.model.update_tracks_for_sequence(f"seq_{count}", track_defs)
            self.assertEqual(len(tracks), count)
            self.assertEqual(self.model.get_selected_count(), 1) # First track default
            self.assertEqual(self.model.get_summary_text(), "1 track selected")

            # Enable all tracks
            for i in range(1, count):
                self.model.toggle_track(f"audio_track_{i}")
            self.assertEqual(self.model.get_selected_count(), count)
            self.assertEqual(self.model.get_summary_text(), "All audio tracks")


if __name__ == "__main__":
    unittest.main()
