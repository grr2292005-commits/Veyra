import os
import sys
import json
import uuid
import time
import shutil
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Any, Optional

# Add engine and models to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.hardware.detector import HardwareDetector
from engine.core.orchestrator import EnhancementOrchestrator, EnhancementJob
from engine.models.factory import ModelFactory
from engine.audio.pipeline import AudioPipeline
from models.manager import ModelManager

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class EngineRequestHandler(BaseHTTPRequestHandler):
    base_dir: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    orchestrator: EnhancementOrchestrator = None
    model_manager: ModelManager = None
    hardware_detector: HardwareDetector = None
    active_jobs: Dict[str, EnhancementJob] = {}
    download_tasks: Dict[str, Dict[str, Any]] = {}
    last_activity: float = time.time()
    last_heartbeat: float = time.time()
    instance_token: str = ""
    script_start_time: float = time.time()
    server_ready_time: float = time.time()
    models_init_duration: float = 0.0

    def _set_cors_headers(self, content_type: str = "application/json"):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Type", content_type)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, data: Any, status_code: int = 200):
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self._set_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _send_error(self, message: str, status_code: int = 400):
        self._send_json({"error": message, "status": "error"}, status_code)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 0:
                raw = self.rfile.read(content_len).decode("utf-8")
                return json.loads(raw)
            return {}
        except Exception as e:
            return None

    def do_GET(self):
        EngineRequestHandler.last_activity = time.time()
        EngineRequestHandler.last_heartbeat = time.time()
        path = self.path.split("?")[0].rstrip("/")

        # Health endpoint (both /health and /api/health)
        if path == "" or path in ("/health", "/api/health"):
            installed_models = [
                mid for mid, m in self.model_manager.list_models().items()
                if m.get("installed")
            ]
            startup_ms = max(1, int(round((EngineRequestHandler.server_ready_time - EngineRequestHandler.script_start_time) * 1000)))
            models_ms = max(1, int(round(EngineRequestHandler.models_init_duration * 1000)))
            self._send_json({
                "status": "ready",
                "healthy": True,
                "service": "Speechify Engine",
                "owner": "speechify",
                "instanceId": self.instance_token,
                "version": "1.0.0",
                "timestamp": time.time(),
                "models": installed_models,
                "models_count": len(installed_models),
                "pid": os.getpid(),
                "timings": {
                    "server_startup_ms": startup_ms,
                    "models_init_ms": models_ms
                }
            })
            return

        # System hardware profile (both /system and /api/system)
        if path in ("/system", "/api/system"):
            profile = self.hardware_detector.get_profile(refresh=True)
            self._send_json(profile)
            return

        # Models catalog (both /models and /api/models)
        if path in ("/models", "/api/models"):
            models = self.model_manager.list_models()
            loc_info = self.model_manager.storage_manager.get_location_info()
            self._send_json({
                "storage_directory": loc_info["storage_directory"],
                "is_managed": loc_info["is_managed"],
                "display_title": loc_info["display_title"],
                "display_subtext": loc_info["display_subtext"],
                "models_count": loc_info["models_count"],
                "models_installed_summary": loc_info["models_installed_summary"],
                "models": models
            })
            return

        if path in ("/config/model-storage", "/api/models/storage-info"):
            loc_info = self.model_manager.storage_manager.get_location_info()
            self._send_json(loc_info)
            return

        if path in ("/api/production-health", "/health/production"):
            from engine.core.health import runProductionHealthCheck
            health_res = runProductionHealthCheck()
            self._send_json(health_res)
            return

        if path.startswith("/api/jobs/"):
            job_id = path.replace("/api/jobs/", "")
            job = self.active_jobs.get(job_id)
            if not job:
                self._send_error(f"Job {job_id} not found", 404)
                return

            response = {
                "job_id": job.job_id,
                "status": job.status,
                "progress_pct": job.progress_pct,
                "progress_msg": job.progress_msg,
                "result": job.result,
                "error": job.error
            }
            self._send_json(response)
            return

        if path.startswith("/api/downloads/"):
            model_id = path.replace("/api/downloads/", "")
            task = self.download_tasks.get(model_id)
            if not task:
                self._send_error(f"Download task for {model_id} not found", 404)
                return
            self._send_json(task)
            return

        self._send_error("Endpoint not found", 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        body = self._read_json_body()
        if body is None:
            self._send_error("Invalid JSON body", 400)
            return

        # Explicit Audio Preparation for Sequence / In-Out Ranges
        if path == "/api/audio/prepare-sequence":
            seq_name = body.get("sequence_name", "Sequence")
            track_name = body.get("track_name")
            track_index = body.get("track_index")
            track_id = body.get("track_id")
            in_sec = float(body.get("in_point_sec", 0.0))
            out_sec = float(body.get("out_point_sec", 0.0))
            clips = body.get("clips", [])
            sample_rate = int(body.get("sample_rate", 48000))

            if out_sec <= in_sec:
                out_sec = in_sec + 1.0

            valid_clips = [c for c in clips if os.path.isfile(c.get("media_path", "") or c.get("mediaPath", ""))]
            if not valid_clips:
                msg = f"Speechify couldn't prepare audio: track {track_name or ''} has no valid audio clips on timeline." if track_name else "Speechify couldn't prepare the audio for enhancement. No valid audio clips found on timeline."
                self._send_error(msg, 400)
                return

            job_id = body.get("job_id") or f"job-{uuid.uuid4().hex[:8]}"
            batch_id = body.get("batch_id")
            track_identifier = body.get("track_id") or (f"track_{track_index}" if track_index is not None else "")

            if batch_id and track_identifier:
                clean_batch = AudioPipeline.sanitize_filename(str(batch_id))
                clean_track = AudioPipeline.sanitize_filename(str(track_identifier))
                temp_dir = os.path.join(self.base_dir, "Speechify", "Temp", f"batch_{clean_batch}", f"track_{clean_track}")
            else:
                temp_dir = os.path.join(self.base_dir, "Speechify", "Temp", job_id)
            os.makedirs(temp_dir, exist_ok=True)

            safe_trk = AudioPipeline.sanitize_filename(track_name) if track_name else ""
            source_filename = f"{safe_trk}_source.wav" if safe_trk else "source.wav"
            source_wav_path = os.path.join(temp_dir, source_filename)

            # Save job metadata
            metadata = {
                "job_id": job_id,
                "batch_id": batch_id,
                "created_at": time.time(),
                "sequence_name": seq_name,
                "sequence_guid": body.get("sequence_guid", ""),
                "track_name": track_name,
                "track_index": track_index,
                "track_id": track_id or track_identifier,
                "in_point_sec": in_sec,
                "out_point_sec": out_sec,
                "sample_rate": sample_rate,
                "valid_clips_count": len(valid_clips),
                "clips": valid_clips
            }

            try:
                AudioPipeline.composite_timeline_audio(
                    clips=valid_clips,
                    in_sec=in_sec,
                    out_sec=out_sec,
                    sample_rate=sample_rate,
                    output_path=source_wav_path
                )
            except Exception as ex:
                self._send_error(f"Speechify couldn't prepare the audio for enhancement: {str(ex)}", 500)
                return

            canonical_source = os.path.join(temp_dir, "source.wav")
            if source_wav_path != canonical_source and not os.path.exists(canonical_source):
                try:
                    import shutil
                    shutil.copy2(source_wav_path, canonical_source)
                except Exception:
                    pass

            # Validate extracted source signal
            try:
                source_diag = AudioPipeline.validate_audio_signal(source_wav_path)
            except Exception as sig_err:
                self._send_error(f"Extracted audio validation failed: {str(sig_err)}", 400)
                return

            metadata["source_diagnostics"] = source_diag

            import hashlib
            try:
                with open(source_wav_path, "rb") as f:
                    metadata["source_sha256_head"] = hashlib.sha256(f.read(65536)).hexdigest()
            except Exception:
                pass

            try:
                # Write source.json as mandated for per-track workspace isolation
                with open(os.path.join(temp_dir, "source.json"), "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

                meta_filename = f"{safe_trk}_metadata.json" if safe_trk else "metadata.json"
                with open(os.path.join(temp_dir, meta_filename), "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
                if meta_filename != "metadata.json":
                    with open(os.path.join(temp_dir, "metadata.json"), "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2)
            except Exception:
                pass

            dur_sec = max(0.1, out_sec - in_sec)
            clip_name = f"{seq_name}_{track_name}" if track_name else seq_name
            self._send_json({
                "success": True,
                "job_id": job_id,
                "batch_id": batch_id,
                "track_id": track_id or track_identifier,
                "source_file": source_wav_path,
                "track_name": track_name,
                "track_index": track_index,
                "duration_sec": dur_sec,
                "clip_name": clip_name,
                "source_diagnostics": source_diag
            })
            return

        # Temporary Workspace Cleanup
        if path == "/api/audio/cleanup-temp":
            job_id = body.get("job_id")
            if job_id:
                temp_dir = os.path.join(self.base_dir, "Speechify", "Temp", job_id)
                if os.path.isdir(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            self._send_json({"success": True})
            return

        if path in ("/api/models/set-storage-path", "/config/model-storage"):
            new_path = body.get("path")
            is_reset = body.get("reset", False)
            if not new_path and not is_reset:
                self._send_error("Missing 'path' parameter", 400)
                return

            try:
                # If reset is true, pass None to set_storage_path to revert to default managed location
                target_path = None if (is_reset or (isinstance(new_path, str) and new_path.lower() == "default")) else new_path
                res = self.model_manager.set_storage_path(target_path)
                self._send_json(res)
            except Exception as e:
                self._send_error(f"Failed to set storage path: {str(e)}", 500)
            return

        # Explicit User-Triggered Model Migration
        if path == "/api/models/migrate":
            source_path = body.get("source_path")
            target_path = body.get("target_path")
            try:
                res = self.model_manager.migrate_models(source_path=source_path, target_path=target_path)
                self._send_json(res)
            except Exception as e:
                self._send_error(f"Migration failed: {str(e)}", 500)
            return

        if path == "/api/models/self-test":
            model_id = body.get("model_id")
            device = body.get("device")
            if not model_id:
                self._send_error("Missing 'model_id'")
                return
            res = self.model_manager.validate_model_runtime(model_id, device=device)
            self._send_json(res)
            return

        if path == "/api/models/download":
            model_id = body.get("model_id")
            if not model_id:
                self._send_error("Missing 'model_id'")
                return

            if model_id in self.download_tasks and self.download_tasks[model_id].get("status") == "downloading":
                self._send_json(self.download_tasks[model_id])
                return

            # Launch background download
            task_info = {
                "model_id": model_id,
                "status": "downloading",
                "progress_pct": 0.0,
                "progress_msg": "Initializing download...",
                "error": None
            }
            self.download_tasks[model_id] = task_info

            def _bg_download():
                def _prog(pct, msg):
                    task_info["progress_pct"] = pct
                    task_info["progress_msg"] = msg

                try:
                    self.model_manager.download_model(model_id, progress_cb=_prog)
                    task_info["progress_msg"] = "Verifying model runtime..."
                    task_info["progress_pct"] = 99.0
                    st = self.model_manager.validate_model_runtime(model_id)
                    if not st.get("success"):
                        raise RuntimeError(f"Model validation self-test failed: {st.get('error', 'unknown error')}")
                    task_info["status"] = "completed"
                    task_info["progress_msg"] = "Ready."
                    task_info["progress_pct"] = 100.0
                except Exception as ex:
                    task_info["status"] = "failed"
                    task_info["error"] = str(ex)

            thread = threading.Thread(target=_bg_download, daemon=True)
            thread.start()

            self._send_json(task_info)
            return

        if path == "/api/enhance":
            source_file = body.get("source_file")
            if not source_file or not os.path.isfile(source_file):
                self._send_error("Speechify couldn't prepare the audio for enhancement: invalid or missing source audio file.", 400)
                return

            job_id = body.get("job_id") or f"job-{uuid.uuid4().hex[:8]}"
            batch_id = body.get("batch_id") or (body.get("metadata", {}).get("batchId") if isinstance(body.get("metadata"), dict) else None)
            track_identifier = body.get("track_id") or (body.get("metadata", {}).get("trackId") if isinstance(body.get("metadata"), dict) else None)

            if batch_id and track_identifier:
                clean_batch = AudioPipeline.sanitize_filename(str(batch_id))
                clean_track = AudioPipeline.sanitize_filename(str(track_identifier))
                job_dir = os.path.join(self.base_dir, "Speechify", "Temp", f"batch_{clean_batch}", f"track_{clean_track}")
            else:
                job_dir = os.path.join(self.base_dir, "Speechify", "Temp", job_id)
            os.makedirs(job_dir, exist_ok=True)

            metadata = body.get("metadata") or {}
            metadata["job_id"] = job_id
            metadata["batch_id"] = batch_id
            metadata["track_id"] = track_identifier
            metadata["received_at"] = time.time()
            metadata["source_file"] = os.path.abspath(source_file)
            metadata["model_id"] = body.get("model_id", "mp_senet")
            metadata["device"] = body.get("device", "auto")
            if os.path.isfile(source_file):
                metadata["source_size"] = os.path.getsize(source_file)
                metadata["source_mtime"] = os.path.getmtime(source_file)
                import hashlib
                try:
                    with open(source_file, "rb") as f:
                        metadata["source_sha256_head"] = hashlib.sha256(f.read(65536)).hexdigest()
                except Exception:
                    pass

            try:
                with open(os.path.join(job_dir, "metadata.json"), "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
            except Exception:
                pass

            job = EnhancementJob(
                job_id=job_id,
                source_file=source_file,
                clip_name=body.get("clip_name"),
                track_index=body.get("track_index"),
                track_name=body.get("track_name") or metadata.get("track_name"),
                in_point_sec=body.get("in_point_sec"),
                out_point_sec=body.get("out_point_sec"),
                sequence_sr=body.get("sequence_sample_rate", 48000),
                model_id=body.get("model_id", "mp_senet"),
                device=body.get("device", "auto"),
                output_dir=body.get("output_dir"),
                job_dir=job_dir,
                metadata=metadata,
                settings=body.get("settings", {})
            )
            self.active_jobs[job_id] = job

            def _bg_worker():
                try:
                    self.orchestrator.run_job(job)
                except Exception as ex:
                    job.status = "failed"
                    job.error = str(ex)
                    job.progress_msg = f"Failed: {str(ex)}"

            worker_thread = threading.Thread(target=_bg_worker, daemon=True)
            worker_thread.start()

            self._send_json({
                "job_id": job_id,
                "status": "queued",
                "message": "Enhancement job initiated successfully."
            })
            return

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[3]
            job = self.active_jobs.get(job_id)
            if not job:
                self._send_error(f"Job {job_id} not found", 404)
                return

            job.cancelled = True
            job.status = "cancelled"
            job.progress_msg = "Cancelled by user."
            self._send_json({"job_id": job_id, "status": "cancelled"})
            return

        if path in ("/heartbeat", "/api/heartbeat"):
            EngineRequestHandler.last_heartbeat = time.time()
            EngineRequestHandler.last_activity = time.time()
            self._send_json({
                "status": "alive",
                "timestamp": time.time(),
                "pid": os.getpid()
            })
            return

        if path in ("/shutdown", "/api/shutdown"):
            t_now = time.strftime("%H:%M:%S")
            print(f"[{t_now}] Shutdown requested. Releasing models and CUDA resources...", flush=True)
            self._send_json({
                "status": "shutting_down",
                "message": "Speechify Engine shutting down cleanly."
            })

            def _stop():
                try:
                    ModelFactory.cleanup_all()
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                except Exception as ex:
                    print(f"[{time.strftime('%H:%M:%S')}] Cleanup warning: {ex}", flush=True)
                finally:
                    # Cleanup lockfile and PID file
                    logs_dir = os.path.join(BASE_DIR, "logs")
                    for fname in ("engine.lock", "engine.pid"):
                        fpath = os.path.join(logs_dir, fname)
                        try:
                            if os.path.isfile(fpath):
                                os.remove(fpath)
                        except Exception:
                            pass
                    time.sleep(0.3)
                    print(f"[{time.strftime('%H:%M:%S')}] Engine stopped.", flush=True)
                    os._exit(0)

            threading.Thread(target=_stop, daemon=True).start()
            return

        self._send_error("Endpoint not found", 404)

    def log_message(self, format, *args):
        # Suppress noisy standard request log lines in normal mode
        return

def run_server(host: str = "127.0.0.1", port: int = 8765, heartbeat_timeout: int = 15, idle_timeout: int = 900, grace_period: int = 30):
    logs_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    lock_file = os.path.join(logs_dir, "engine.lock")
    pid_file = os.path.join(logs_dir, "engine.pid")

    pid = os.getpid()
    instance_id = f"sp-inst-{uuid.uuid4().hex[:8]}"
    server_start_time = time.time()

    EngineRequestHandler.instance_token = instance_id
    EngineRequestHandler.last_heartbeat = server_start_time
    EngineRequestHandler.last_activity = server_start_time

    # Write engine.lock and engine.pid
    lock_data = {
        "pid": pid,
        "owner": "speechify",
        "instanceId": instance_id,
        "startedAt": server_start_time,
        "port": port
    }
    try:
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, indent=2)
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception as e:
        print(f"Warning: Could not write lockfile: {e}", flush=True)

    def cleanup_files():
        try:
            if os.path.isfile(lock_file):
                os.remove(lock_file)
            if os.path.isfile(pid_file):
                os.remove(pid_file)
        except Exception:
            pass

    import atexit
    atexit.register(cleanup_files)

    # Startup orphan temp cleanup (Section 130)
    temp_dir = os.path.join(BASE_DIR, "Speechify", "Temp")
    if os.path.isdir(temp_dir):
        try:
            now_t = time.time()
            for entry in os.listdir(temp_dir):
                if entry.startswith("job-"):
                    epath = os.path.join(temp_dir, entry)
                    if os.path.isdir(epath):
                        # Clean if older than 1 hour (3600 seconds)
                        if (now_t - os.path.getmtime(epath)) > 3600:
                            shutil.rmtree(epath, ignore_errors=True)
        except Exception as ex:
            print(f"[Engine] Temp cleanup notice: {ex}", flush=True)

    EngineRequestHandler.script_start_time = server_start_time
    t_m0 = time.time()
    mgr = ModelManager()
    EngineRequestHandler.models_init_duration = time.time() - t_m0

    orch = EnhancementOrchestrator(mgr)
    det = HardwareDetector()

    EngineRequestHandler.model_manager = mgr
    EngineRequestHandler.orchestrator = orch
    EngineRequestHandler.hardware_detector = det

    server_address = (host, port)
    try:
        httpd = ThreadedHTTPServer(server_address, EngineRequestHandler)
    except OSError as os_err:
        t_err = time.strftime("%H:%M:%S")
        print(f"[{t_err}] Port conflict detected on http://{host}:{port}: {os_err}", flush=True)
        cleanup_files()
        # Exit with meaningful code: 2 for port conflict / already occupied
        sys.exit(2)

    EngineRequestHandler.server_ready_time = time.time()

    t_start = time.strftime("%H:%M:%S")
    storage_display = mgr.get_storage_path() if hasattr(mgr, "get_storage_path") else getattr(mgr, "storage_path", "models/storage")
    bind_ms = int(round((EngineRequestHandler.server_ready_time - server_start_time) * 1000))
    print(f"[{t_start}] Speechify Local AI Engine starting on http://{host}:{port}", flush=True)
    print(f"[{t_start}] PID: {pid} | Instance: {instance_id} | Storage: {storage_display}", flush=True)
    print(f"[{t_start}] Engine listening and ready (bound in {bind_ms}ms).", flush=True)

    # Asynchronously pre-warm hardware capabilities in background so readiness is never delayed
    def _warmup_hardware():
        try:
            det.get_profile()
        except Exception:
            pass
    threading.Thread(target=_warmup_hardware, daemon=True).start()

    # Watchdog thread: monitors heartbeat pings and idle timeouts
    def _watchdog():
        while True:
            time.sleep(2)
            now = time.time()

            # If an active enhancement job is running, do not time out
            running_jobs = any(
                j.status in ("queued", "running", "processing")
                for j in EngineRequestHandler.active_jobs.values()
            )
            if running_jobs:
                EngineRequestHandler.last_heartbeat = now
                EngineRequestHandler.last_activity = now
                continue

            # Heartbeat check (activated after grace_period to allow panel connection)
            if heartbeat_timeout > 0 and (now - server_start_time) > grace_period:
                elapsed_since_hb = now - EngineRequestHandler.last_heartbeat
                if elapsed_since_hb > heartbeat_timeout:
                    t_str = time.strftime("%H:%M:%S")
                    print(f"[{t_str}] [Watchdog] Heartbeat stopped ({elapsed_since_hb:.1f}s > {heartbeat_timeout}s). Auto-terminating...", flush=True)
                    try:
                        ModelFactory.cleanup_all()
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                    cleanup_files()
                    os._exit(0)

            # Idle timeout check
            if idle_timeout > 0:
                idle_duration = now - EngineRequestHandler.last_activity
                if idle_duration > idle_timeout:
                    t_str = time.strftime("%H:%M:%S")
                    print(f"[{t_str}] [Watchdog] Engine idle for {idle_duration:.0f}s. Shutting down...", flush=True)
                    cleanup_files()
                    os._exit(0)

    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"[{time.strftime('%H:%M:%S')}] Shutting down Speechify Engine...", flush=True)
    finally:
        cleanup_files()
        httpd.server_close()

if __name__ == "__main__":
    port = 8765
    heartbeat_timeout = 15 # 15 seconds without heartbeat -> auto-shutdown
    idle_timeout = 900      # 15 minutes without any activity -> auto-shutdown
    grace_period = 30      # 30s grace period after startup
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            heartbeat_timeout = int(sys.argv[2])
        except ValueError:
            pass
    if len(sys.argv) > 3:
        try:
            idle_timeout = int(sys.argv[3])
        except ValueError:
            pass
    if len(sys.argv) > 4:
        try:
            grace_period = int(sys.argv[4])
        except ValueError:
            pass
    run_server(port=port, heartbeat_timeout=heartbeat_timeout, idle_timeout=idle_timeout, grace_period=grace_period)

