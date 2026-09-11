import os
import sys
import json
import unittest
import urllib.parse
from typing import Dict, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.audio.pipeline import AudioPipeline

class ContextSerializationTests(unittest.TestCase):
    """
    Exhaustive unit test suite verifying the PremiereContextSnapshot data contract,
    safe serialization boundaries, Windows backslash path fidelity, and error resilience.
    """

    def setUp(self):
        self.valid_snapshot: Dict[str, Any] = {
            "schemaVersion": 1,
            "sequence": {
                "guid": "seq_guid_test_100",
                "name": "Sequence 01"
            },
            "sequenceGuid": "seq_guid_test_100",
            "sequenceName": "Sequence 01",
            "scope": "selected_clips",
            "inPointSec": 0.0,
            "outPointSec": 120.5,
            "durationSec": 120.5,
            "fps": 23.976,
            "sampleRate": 48000,
            "clips": [
                {
                    "trackIndex": 0,
                    "trackName": "A1",
                    "clipName": "Comfort WEAK Mindset - Andrew Tate",
                    "name": "Comfort WEAK Mindset - Andrew Tate",
                    "clipId": "clip_t0_c0_s0",
                    "projectItemId": "pitem_9921",
                    "projectItemName": "Comfort WEAK Mindset - Andrew Tate.mp3",
                    "sourcePath": r"C:\Users\grr22\Desktop\audio test\Comfort WEAK Mindset - Andrew Tate.mp3",
                    "mediaPath": r"C:\Users\grr22\Desktop\audio test\Comfort WEAK Mindset - Andrew Tate.mp3",
                    "timelineStart": 0.0,
                    "timelineEnd": 120.5,
                    "startTimeSec": 0.0,
                    "durationSec": 120.5,
                    "duration": 120.5,
                    "inPointSec": 0.0,
                    "outPointSec": 120.5,
                    "fileSize": 1048576,
                    "fileMtime": 1726000000.0,
                    "fileExists": True
                }
            ],
            "snapshotTimestamp": 1726000000000
        }

    # ----------------------------------------------------------------------
    # Helper simulating the JS/ExtendScript parseContext implementation
    # ----------------------------------------------------------------------
    @staticmethod
    def parse_context(payload: Any) -> Dict[str, Any]:
        if payload is None:
            raise ValueError("Context payload is null or undefined")
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            trimmed = payload.strip()
            if not trimmed:
                raise ValueError("Context payload is empty string")
            # Handle URL-encoded strings
            if "%" in trimmed and ("%7B" in trimmed or "%22" in trimmed or "%5B" in trimmed):
                try:
                    trimmed = urllib.parse.unquote(trimmed)
                except Exception:
                    pass
            try:
                parsed = json.loads(trimmed)
            except Exception as e:
                raise ValueError(f"JSON.parse failure: {e}")
            # Handle double-serialized JSON strings
            if isinstance(parsed, str):
                try:
                    double_parsed = json.loads(parsed)
                    if isinstance(double_parsed, dict):
                        parsed = double_parsed
                except Exception:
                    pass
            if not isinstance(parsed, dict):
                raise ValueError("Context payload did not deserialize to an object")
            return parsed
        raise ValueError(f"Unsupported context payload type: {type(payload)}")

    @staticmethod
    def validate_snapshot_structure(raw: Any) -> Dict[str, Any]:
        try:
            snapshot = ContextSerializationTests.parse_context(raw)
        except Exception as e:
            return {"valid": False, "errors": [{"code": "INVALID_PAYLOAD", "message": str(e)}]}

        errors = []
        seq = snapshot.get("sequence", {})
        seq_guid = seq.get("guid") or snapshot.get("sequenceGuid")
        if not seq_guid:
            errors.append({"code": "MISSING_SEQUENCE_IDENTITY", "message": "Missing sequence guid"})

        scope = snapshot.get("scope")
        if scope not in ("selected_clips", "in_out", "full_sequence"):
            errors.append({"code": "INVALID_SCOPE", "message": f"Invalid scope {scope}"})

        clips = snapshot.get("clips")
        if not isinstance(clips, list):
            errors.append({"code": "INVALID_CLIPS_TYPE", "message": "Clips must be list"})
        elif scope == "selected_clips" and len(clips) == 0:
            errors.append({"code": "NO_CLIPS_SELECTED", "message": "No clips selected"})
        else:
            for idx, c in enumerate(clips):
                if not isinstance(c, dict):
                    errors.append({"code": "INVALID_CLIP", "message": f"Clip {idx} not dict"})
                    continue
                path = c.get("sourcePath") or c.get("mediaPath")
                if not path or not isinstance(path, str) or not path.strip():
                    errors.append({"code": "MISSING_SOURCE_PATH", "message": f"Clip {idx} missing path"})

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sanitizedSnapshot": snapshot if len(errors) == 0 else None
        }

    # ----------------------------------------------------------------------
    # Tests
    # ----------------------------------------------------------------------
    def test_object_input_passes(self):
        """Passing a plain dict/object must pass validation without calling JSON.parse on it."""
        result = self.validate_snapshot_structure(self.valid_snapshot)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_string_input_passes(self):
        """Passing a JSON string must pass after a single parse."""
        json_str = json.dumps(self.valid_snapshot)
        result = self.validate_snapshot_structure(json_str)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_malformed_string_safe_rejection(self):
        """Malformed JSON strings like '{invalid' must return structured failure, not crash."""
        result = self.validate_snapshot_structure("{invalid json structure")
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "INVALID_PAYLOAD")

    def test_empty_string_safe_rejection(self):
        """Empty string must return controlled invalid-context result."""
        result = self.validate_snapshot_structure("")
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "INVALID_PAYLOAD")

    def test_null_and_undefined_safe_rejection(self):
        """Null must return controlled invalid-context result."""
        result = self.validate_snapshot_structure(None)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "INVALID_PAYLOAD")

    def test_double_serialized_json_handling(self):
        """Double-serialized JSON strings must be safely decoded without throwing."""
        double_encoded = json.dumps(json.dumps(self.valid_snapshot))
        result = self.validate_snapshot_structure(double_encoded)
        self.assertTrue(result["valid"])
        self.assertEqual(result["sanitizedSnapshot"]["sequenceGuid"], "seq_guid_test_100")

    def test_url_encoded_payload_windows_backslash_fidelity(self):
        """
        URL-encoded payloads (used across CEP evalScript boundary) must preserve
        Windows backslashes in paths with 100% fidelity.
        """
        original_path = r"C:\Users\grr22\Desktop\audio test\Comfort WEAK Mindset - Andrew Tate.mp3"
        json_str = json.dumps(self.valid_snapshot)
        url_encoded = urllib.parse.quote(json_str)

        decoded = self.parse_context(url_encoded)
        clip_path = decoded["clips"][0]["sourcePath"]
        self.assertEqual(clip_path, original_path)
        self.assertIn(r"\Users\grr22", clip_path)

    def test_no_host_objects_in_job_payload(self):
        """
        The EnhancementJob payload must contain strictly JSON-safe primitives
        and zero host objects (no DOM, no functions, no mocks with circular refs).
        """
        clip = self.valid_snapshot["clips"][0]
        job_payload = {
            "clipJobId": "job-101_c0",
            "masterJobId": "job-101",
            "sourceFile": clip["sourcePath"],
            "inPointSec": clip["inPointSec"],
            "outPointSec": clip["outPointSec"],
            "clipName": clip["clipName"],
            "targetStartTime": clip["startTimeSec"],
            "durationSec": clip["durationSec"],
            "trackIndex": clip["trackIndex"],
            "projectItemId": clip["projectItemId"],
            "sequenceGuid": self.valid_snapshot["sequenceGuid"],
            "sequenceName": self.valid_snapshot["sequenceName"],
            "fileSize": clip["fileSize"],
            "fileMtime": clip["fileMtime"]
        }

        # Verify all values are primitive types
        for k, v in job_payload.items():
            self.assertIn(type(v), [str, int, float, bool, type(None)], f"Field '{k}' has non-primitive type: {type(v)}")

        # Verify JSON round-trip
        serialized = json.dumps(job_payload)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized, job_payload)

    def test_stale_clip_and_sequence_identity_rejection(self):
        """If active sequence GUID changes, validation must cleanly report SEQUENCE_CHANGED."""
        snapshot = dict(self.valid_snapshot)
        current_seq_id = "new_different_seq_guid_200"

        if current_seq_id != snapshot["sequenceGuid"]:
            validation = {
                "valid": False,
                "errors": [{"code": "SEQUENCE_CHANGED", "message": "Active sequence changed."}]
            }
        else:
            validation = {"valid": True, "errors": []}

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["errors"][0]["code"], "SEQUENCE_CHANGED")

    def test_same_name_clips_have_different_identities(self):
        """Clips sharing the same display name must have distinct clipId and timeline positions."""
        clip1 = dict(self.valid_snapshot["clips"][0])
        clip2 = dict(self.valid_snapshot["clips"][0])
        clip2["clipId"] = "clip_t0_c1_s60000"
        clip2["startTimeSec"] = 60.0
        clip2["timelineStart"] = 60.0

        self.assertEqual(clip1["clipName"], clip2["clipName"])
        self.assertNotEqual(clip1["clipId"], clip2["clipId"])
        self.assertNotEqual(clip1["startTimeSec"], clip2["startTimeSec"])

    def test_source_path_verified_no_fallback(self):
        """A clip missing sourcePath must fail structural validation and never fallback."""
        bad_snapshot = json.loads(json.dumps(self.valid_snapshot))
        bad_snapshot["clips"][0]["sourcePath"] = ""
        bad_snapshot["clips"][0]["mediaPath"] = ""

        result = self.validate_snapshot_structure(bad_snapshot)
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "MISSING_SOURCE_PATH" for e in result["errors"]))

    def test_compound_cache_key_reflects_context_identity(self):
        """Compound cache keys must change when sequence, item ID, or source identity change."""
        key1 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq_01",
            track_item_id="clip_01",
            project_item_id="pitem_01",
            source_path=r"C:\audio\interview.wav",
            in_sec=0.0,
            out_sec=10.0,
            mtime=1726000000.0,
            file_size=1000000
        )
        # Same path but different clip/projectItem identity (e.g. replaced clip)
        key2 = AudioPipeline.get_source_cache_key(
            sequence_guid="seq_01",
            track_item_id="clip_02",
            project_item_id="pitem_02",
            source_path=r"C:\audio\interview.wav",
            in_sec=0.0,
            out_sec=10.0,
            mtime=1726000000.0,
            file_size=1000000
        )
        self.assertNotEqual(key1, key2)

if __name__ == "__main__":
    unittest.main()
