import unittest
import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
import tempfile
import numpy as np
import soundfile as sf

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.server import ThreadedHTTPServer, EngineRequestHandler
from engine.hardware.detector import HardwareDetector
from engine.core.orchestrator import EnhancementOrchestrator
from models.manager import ModelManager

class TestServerAPI(unittest.TestCase):
    server = None
    server_thread = None
    port = 8769
    base_url = f"http://127.0.0.1:{port}"

    @classmethod
    def setUpClass(cls):
        mgr = ModelManager()
        orch = EnhancementOrchestrator(mgr)
        det = HardwareDetector()

        EngineRequestHandler.model_manager = mgr
        EngineRequestHandler.orchestrator = orch
        EngineRequestHandler.hardware_detector = det

        cls.server = ThreadedHTTPServer(("127.0.0.1", cls.port), EngineRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()

    def _get(self, path):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_health_endpoint(self):
        status, data = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertIn(data["status"], ("healthy", "ready"))
        self.assertEqual(data["service"], "Speechify Engine")

    def test_system_endpoint(self):
        status, data = self._get("/api/system")
        self.assertEqual(status, 200)
        self.assertIn("cpu", data)
        self.assertIn("ram", data)
        self.assertIn("gpu", data)
        self.assertIsInstance(data["gpu"], dict)
        self.assertIn("available", data["gpu"])
        self.assertIn("available_devices", data)
        self.assertIsInstance(data["available_devices"], list)
        device_ids = [d["id"] for d in data["available_devices"]]
        self.assertIn("auto", device_ids)
        self.assertIn("cpu", device_ids)
        if data["gpu"]["available"]:
            self.assertTrue(any("cuda" in d for d in device_ids))

    def test_prepare_sequence_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sr = 48000
            clip1 = os.path.join(tmp_dir, "clip1.wav")
            clip2 = os.path.join(tmp_dir, "clip2.wav")
            sf.write(clip1, np.random.uniform(-0.2, 0.2, sr).astype(np.float32), sr)
            sf.write(clip2, np.random.uniform(-0.2, 0.2, sr).astype(np.float32), sr)

            payload = {
                "sequence_name": "TestSequence",
                "in_point_sec": 0.0,
                "out_point_sec": 4.0,
                "sample_rate": 48000,
                "clips": [
                    {"mediaPath": clip1, "startTimeSec": 0.0, "durationSec": 1.0, "inPointSec": 0.0, "outPointSec": 1.0},
                    {"mediaPath": clip2, "startTimeSec": 2.0, "durationSec": 1.0, "inPointSec": 0.0, "outPointSec": 1.0}
                ]
            }

            status, data = self._post("/api/audio/prepare-sequence", payload)
            self.assertEqual(status, 200)
            self.assertTrue(data["success"])
            self.assertIn("source_file", data)
            self.assertTrue(os.path.isfile(data["source_file"]))
            self.assertIn("job_id", data)

            # Validate audio duration
            info = sf.info(data["source_file"])
            self.assertEqual(info.samplerate, 48000)
            self.assertAlmostEqual(info.duration, 4.0, delta=0.1)

            # Cleanup temp directory
            status_c, data_c = self._post("/api/audio/cleanup-temp", {"job_id": data["job_id"]})
            self.assertEqual(status_c, 200)
            self.assertTrue(data_c["success"])
            self.assertFalse(os.path.isfile(data["source_file"]))

    def test_enhance_validation_error(self):
        try:
            self._post("/api/enhance", {})
            self.fail("Expected HTTPError 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            err_body = json.loads(e.read().decode("utf-8"))
            self.assertIn("Speechify couldn't prepare the audio", err_body["error"])

    def test_enhance_job_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a 1-second 48kHz test WAV
            sr = 48000
            test_wav = os.path.join(tmp_dir, "test_speech.wav")
            audio = np.random.uniform(-0.3, 0.3, sr).astype(np.float32)
            sf.write(test_wav, audio, sr)

            # Submit enhance job with deepfilternet3 (fastest test)
            status, res = self._post("/api/enhance", {
                "source_file": test_wav,
                "model_id": "deepfilternet3",
                "sequence_sample_rate": 48000,
                "output_dir": tmp_dir
            })
            self.assertEqual(status, 200)
            job_id = res["job_id"]
            self.assertTrue(job_id.startswith("job-"))

            # Poll for job status
            completed = False
            for _ in range(30):
                time.sleep(0.3)
                s, job_info = self._get(f"/api/jobs/{job_id}")
                self.assertEqual(s, 200)
                if job_info["status"] == "completed":
                    completed = True
                    self.assertIn("result", job_info)
                    self.assertTrue(os.path.exists(job_info["result"]["enhanced_file"]))
                    break
                elif job_info["status"] == "failed":
                    self.fail(f"Job failed: {job_info.get('error')}")

            self.assertTrue(completed, "Job did not complete within timeout")

if __name__ == "__main__":
    unittest.main()
