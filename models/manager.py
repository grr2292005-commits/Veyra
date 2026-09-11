import os
import sys
import json
import shutil
import hashlib
import urllib.request
import threading
from typing import Dict, Any, Optional, Callable

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.runtime.model_discovery import ModelDiscovery

from models.storage_manager import ModelStorageManager

class ModelManager:
    """
    Central manager for model storage, registry querying, checkpoint validation,
    and user-customizable storage directory configuration.
    Delegates to ModelStorageManager as authoritative single source of truth.
    """
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = os.path.abspath(base_dir)
        self.storage_manager = ModelStorageManager(self.base_dir)
        self.registry_data = self.storage_manager.registry_data

    @property
    def storage_path(self) -> str:
        return self.storage_manager.get_storage_path()

    def get_storage_path(self) -> str:
        """Returns the authoritative active model storage directory path."""
        return self.storage_manager.get_storage_path()

    def verify_checkpoint(self, model_id: str) -> bool:
        """Checks if the model checkpoint exists and is non-empty in active storage."""
        return self.storage_manager.is_installed(model_id)

    def scan_current_storage(self) -> Dict[str, Any]:
        return self.storage_manager.scan_current_storage()

    def set_storage_path(self, new_path: str) -> Dict[str, Any]:
        return self.storage_manager.set_storage_path(new_path)

    def migrate_models(self, source_path: Optional[str] = None, target_path: Optional[str] = None) -> Dict[str, Any]:
        return self.storage_manager.migrate_models(source_path=source_path, target_path=target_path)

    def get_model_file_path(self, model_id: str) -> Optional[str]:
        return self.storage_manager.get_model_file_path(model_id)

    def is_installed(self, model_id: str) -> bool:
        return self.storage_manager.is_installed(model_id)

    def list_models(self) -> Dict[str, Any]:
        return self.storage_manager.list_models()

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        models = self.list_models()
        if model_id in models:
            m = models[model_id]
            return {
                **m,
                "path": m.get("local_path")
            }
        return None


    _download_lock = threading.Lock()
    _active_downloads: Dict[str, Any] = {}

    def download_model(
        self,
        model_id: str,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        Downloads a model using HTTPS with progress reporting,
        cancellation checks, SHA256 checksum verification, and atomic commit.
        Guards against duplicate simultaneous downloads.
        """
        model_meta = self.registry_data["models"].get(model_id)
        if not model_meta:
            raise ValueError(f"Unknown model ID: {model_id}")

        with self._download_lock:
            if model_id in self._active_downloads:
                return {"success": False, "status": "already_downloading", "message": f"Download already in progress for {model_id}"}
            self._active_downloads[model_id] = True

        from models.storage_manager import FOLDER_ALIASES
        canonical_folder = FOLDER_ALIASES.get(model_id, [model_id])[0]
        model_dir = os.path.join(self.storage_path, canonical_folder)
        os.makedirs(model_dir, exist_ok=True)
        dest_path = os.path.join(model_dir, model_meta["checkpoint_filename"])
        temp_dest = dest_path + f".download.{os.getpid()}"

        url = model_meta["download_url"]
        expected_size = model_meta.get("checkpoint_size_bytes", 0)
        expected_sha256 = model_meta.get("sha256")

        # Custom download hook
        def reporthook(block_num, block_size, total_size):
            if cancel_check and cancel_check():
                raise InterruptedError("Download cancelled by user.")
            if total_size > 0:
                percent = min(100.0, (block_num * block_size / total_size) * 100.0)
            elif expected_size > 0:
                percent = min(100.0, (block_num * block_size / expected_size) * 100.0)
            else:
                percent = 50.0
            if progress_cb:
                progress_cb(percent, f"Downloading {model_meta['name']} ({percent:.1f}%)...")

        try:
            if cancel_check and cancel_check():
                raise InterruptedError("Download cancelled by user.")

            if progress_cb:
                progress_cb(0.0, f"Connecting to {url}...")
            urllib.request.urlretrieve(url, temp_dest, reporthook=reporthook)

            # Validate file size
            actual_size = os.path.getsize(temp_dest)
            if expected_size > 0 and actual_size < expected_size * 0.95:
                raise IOError(f"Downloaded file incomplete: {actual_size} bytes, expected {expected_size}")

            # Validate SHA256 checksum if specified
            if expected_sha256:
                if progress_cb:
                    progress_cb(95.0, "Verifying checksum integrity...")
                hasher = hashlib.sha256()
                with open(temp_dest, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                actual_sha256 = hasher.hexdigest()
                if actual_sha256.lower() != expected_sha256.lower():
                    raise ValueError(
                        f"Checksum verification failed for {model_id}! "
                        f"Expected {expected_sha256}, got {actual_sha256}"
                    )

            # Atomic Commit
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.replace(temp_dest, dest_path)

            if progress_cb:
                progress_cb(100.0, f"{model_meta['name']} installed successfully.")

            return {
                "success": True,
                "model_id": model_id,
                "installed_path": dest_path,
                "size_bytes": actual_size
            }
        except Exception as e:
            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except Exception:
                    pass
            raise e
        finally:
            with self._download_lock:
                if model_id in self._active_downloads:
                    del self._active_downloads[model_id]

    def validate_model_runtime(self, model_id: str, device: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs lightweight model self-test (Section 31):
        1. Resolves checkpoint path from active storage.
        2. Instantiates model adapter via ModelFactory.
        3. Calls adapter.self_test().
        4. Returns status ('Ready' vs 'Needs attention').
        """
        ckpt_path = self.get_model_file_path(model_id)
        if not ckpt_path or not os.path.isfile(ckpt_path):
            return {
                "success": False,
                "model_id": model_id,
                "status": "Not installed",
                "error": "Checkpoint file not found in active model storage."
            }

        meta = self.registry_data["models"].get(model_id, {})
        try:
            from engine.models.factory import ModelFactory
            adapter = ModelFactory.create_adapter(model_id, ckpt_path, device=device)
            res = adapter.self_test(ckpt_path, device=device)
            res["model_id"] = model_id
            return res
        except Exception as ex:
            return {
                "success": False,
                "model_id": model_id,
                "status": "Needs attention",
                "error": str(ex)
            }

if __name__ == "__main__":
    mgr = ModelManager()
    print("Storage directory:", mgr.get_storage_path())
    models = mgr.list_models()
    for mid, m in models.items():
        print(f"[{mid}] Installed: {m['installed']} | Path: {m['local_path']}")
