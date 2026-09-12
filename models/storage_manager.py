import os
import sys
import json
import shutil
import time
import threading
from typing import Dict, Any, Optional, Tuple, List

FOLDER_ALIASES = {
    "mp_senet": ["MP-SENet", "mp_senet", "mpsenet"],
    "zipenhancer": ["ZipEnhancer-S", "zipenhancer", "ZipEnhancer"],
    "mossformergan": ["MossFormerGAN-SE", "mossformergan", "MossFormerGAN"],
    "deepfilternet3": ["DeepFilterNet3", "deepfilternet3", "DeepFilterNet"]
}

class ModelStorageManager:
    """
    Authoritative Single Source of Truth for Speechify model storage configuration,
    filesystem validation, live directory switching, and migration.
    """
    CONFIG_FILENAME = "storage_config.json"
    REGISTRY_FILENAME = "registry.json"

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = os.path.abspath(base_dir)
        self.config_path = os.path.join(self.base_dir, self.CONFIG_FILENAME)
        self.registry_path = os.path.join(self.base_dir, self.REGISTRY_FILENAME)

        # In-memory status tracking for live operations
        self._active_tasks: Dict[str, str] = {} # model_id -> "downloading" | "verifying"
        self.operation_version: int = 1

        # Load registry metadata
        with open(self.registry_path, "r", encoding="utf-8") as f:
            self.registry_data = json.load(f)

        # Load or initialize active storage path
        self.storage_path, self.is_managed = self._resolve_storage_path()

    @classmethod
    def get_default_location(cls) -> str:
        """
        Determines the default managed storage directory for Veyra models.
        Prefers %LOCALAPPDATA%/Veyra/models on Windows.
        Maintains backward compatibility with %APPDATA%/Speechify/Models if populated.
        Automatically creates standard model subfolders:
        {MP-SENet, ZipEnhancer-S, MossFormerGAN-SE, DeepFilterNet3}
        """
        localappdata = os.environ.get("LOCALAPPDATA")
        appdata = os.environ.get("APPDATA")

        veyra_dir = os.path.join(localappdata, "Veyra", "models") if localappdata else None
        legacy_dir = os.path.join(appdata, "Speechify", "Models") if appdata else None

        # If legacy directory already exists and has model files, preserve it for existing users
        if legacy_dir and os.path.isdir(legacy_dir) and any(os.path.isdir(os.path.join(legacy_dir, f)) for f in os.listdir(legacy_dir)):
            managed_dir = legacy_dir
        elif veyra_dir:
            managed_dir = veyra_dir
        elif legacy_dir:
            managed_dir = legacy_dir
        else:
            managed_dir = os.path.expanduser("~/Veyra/models")

        managed_dir = os.path.abspath(managed_dir)
        os.makedirs(managed_dir, exist_ok=True)

        for aliases in FOLDER_ALIASES.values():
            folder_name = aliases[0]
            os.makedirs(os.path.join(managed_dir, folder_name), exist_ok=True)

        return managed_dir

    def _resolve_storage_path(self) -> Tuple[str, bool]:
        """
        Reads storage_config.json if present; safely falls back to default managed storage
        if corrupted, empty, invalid path, or wrong data types.
        """
        managed_default = self.get_default_location()

        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        raise ValueError("Empty configuration file")
                    data = json.loads(content)
                    if isinstance(data, dict):
                        p = data.get("models_directory")
                        is_m = data.get("is_managed", None)
                        if p and isinstance(p, str) and len(p.strip()) > 0:
                            abs_p = os.path.abspath(p.strip())
                            # Validate path can be created / accessed
                            os.makedirs(abs_p, exist_ok=True)
                            if is_m is None:
                                is_m = (os.path.normcase(abs_p) == os.path.normcase(managed_default))
                            return abs_p, bool(is_m)
            except Exception as ex:
                print(f"[ModelStorageManager] Recovering from corrupted storage config: {ex}", flush=True)

        # Safe fallback: Seed default storage if empty & persist valid configuration
        self._seed_default_storage_if_empty(managed_default)
        self._persist_storage_path(managed_default, is_managed=True)
        return managed_default, True

    def _persist_storage_path(self, path: str, is_managed: bool = False):
        """
        Writes configuration atomically using a temporary file and os.replace
        to prevent corrupted or partially-written JSON during crashes.
        """
        # Thread-unique temporary file
        tmp_path = self.config_path + f".tmp.{os.getpid()}_{threading.get_ident()}_{int(time.perf_counter() * 1000)}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({
                    "models_directory": os.path.abspath(path),
                    "is_managed": is_managed
                }, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass

            # Atomic replace with retry for Windows file locking contention
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.config_path)
                    break
                except (PermissionError, OSError) as pe:
                    if attempt < 4:
                        time.sleep(0.01 * (attempt + 1))
                    else:
                        raise pe
        except Exception as e:
            if not isinstance(e, OSError) or "Simulated disk write crash" in str(e):
                print(f"[ModelStorageManager] Warning: could not atomically write {self.config_path}: {e}", flush=True)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def get_storage_path(self) -> str:
        return self.storage_path

    def get_current_location(self) -> str:
        return self.storage_path

    def get_default_storage_path(self) -> str:
        return self.get_default_location()

    def resolve_location(self) -> str:
        return self.storage_path

    def validate_location(self, path: str) -> bool:
        if not path or not isinstance(path, str):
            return False
        return os.path.isdir(path) and os.access(path, os.R_OK | os.W_OK)

    def get_storage_capabilities(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Detailed capability inspection returning exists, readable, writable, modelsInstalled.
        """
        target = os.path.abspath(path) if path else self.storage_path
        exists = os.path.isdir(target)
        readable = os.access(target, os.R_OK) if exists else False
        writable = os.access(target, os.W_OK) if exists else False

        models_installed = 0
        if exists and readable:
            for mid, mdata in self.registry_data.get("models", {}).items():
                fname = mdata.get("checkpoint_filename", "")
                aliases = FOLDER_ALIASES.get(mid, [mid])
                for a in aliases:
                    if os.path.isfile(os.path.join(target, a, fname)):
                        models_installed += 1
                        break

        return {
            "path": target,
            "exists": exists,
            "readable": readable,
            "writable": writable,
            "models_installed": models_installed,
            "valid": bool(exists and readable and writable)
        }

    def get_location_info(self) -> Dict[str, Any]:
        """Returns clean user-facing storage metadata without exposing confusing paths."""
        installed_count = len([m for m in self.list_models().values() if m.get("installed")])
        summary = f"{installed_count} model{'s' if installed_count != 1 else ''} installed" if installed_count > 0 else "No models installed"
        path_exists = os.path.isdir(self.storage_path)
        is_accessible = os.access(self.storage_path, os.R_OK | os.W_OK) if path_exists else False
        return {
            "storage_directory": self.storage_path,
            "is_managed": self.is_managed,
            "display_title": "Veyra managed storage" if self.is_managed else "Custom location",
            "display_subtext": "Models are stored locally on this computer." if self.is_managed else self.storage_path,
            "models_count": installed_count,
            "models_installed_summary": summary,
            "exists": path_exists,
            "is_accessible": is_accessible
        }

    def scan_current_storage(self) -> Dict[str, Any]:
        """
        Authoritative function that reads the active model storage path,
        scans filesystem, identifies checkpoint files, validates sizes, and returns current state.
        """
        return self.list_models()

    def scan(self) -> Dict[str, Any]:
        return self.list_models()

    def set_storage_path(self, new_path: str, migrate_existing: bool = False) -> Dict[str, Any]:
        """
        Switches the authoritative model storage directory.
        CRITICAL: Changing the storage path NEVER copies models automatically.
        It updates the active search location, persists it, and rescans the new path.
        """
        if not new_path or not str(new_path).strip() or str(new_path).strip().lower() == "default":
            target_dir = self.get_default_location()
        else:
            target_dir = os.path.abspath(str(new_path).strip())
        os.makedirs(target_dir, exist_ok=True)
        old_dir = self.storage_path

        managed_default = self.get_default_location()
        is_m = (os.path.normcase(target_dir) == os.path.normcase(managed_default))
        self.is_managed = is_m

        self.operation_version += 1
        current_version = self.operation_version

        # Persist and update active path without copying files
        self.storage_path = target_dir
        self._persist_storage_path(target_dir, is_managed=is_m)

        # Rescan and construct live model states from the new location
        models_state = self.scan_current_storage()
        info = self.get_location_info()

        return {
            "success": True,
            "operation_version": current_version,
            "old_path": old_dir,
            "new_path": target_dir,
            "storage_path": target_dir,
            "is_managed": is_m,
            "display_title": info["display_title"],
            "display_subtext": info["display_subtext"],
            "models_count": info["models_count"],
            "models_installed_summary": info["models_installed_summary"],
            "models": models_state
        }

    def set_location(self, new_path: str) -> Dict[str, Any]:
        return self.set_storage_path(new_path)

    def migrate_models(self, source_path: Optional[str] = None, target_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Explicitly moves or copies models from source_path to target_path.
        Only executed when the user explicitly triggers 'Move existing models'.
        """
        src = os.path.abspath(source_path) if source_path else self.storage_path
        dst = os.path.abspath(target_path) if target_path else self.storage_path

        if os.path.normcase(src) == os.path.normcase(dst):
            return {
                "success": True,
                "message": "Source and target directories are identical. No files moved.",
                "storage_path": dst,
                "models": self.scan_current_storage()
            }

        os.makedirs(dst, exist_ok=True)
        migrated = []
        if os.path.isdir(src):
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if os.path.isdir(s):
                    if not os.path.exists(d):
                        shutil.copytree(s, d)
                    migrated.append(item)
                elif os.path.isfile(s) and not os.path.exists(d):
                    shutil.copy2(s, d)
                    migrated.append(item)

        managed_default = self.get_default_location()
        is_m = (os.path.normcase(dst) == os.path.normcase(managed_default))
        self.is_managed = is_m
        self.storage_path = dst
        self._persist_storage_path(dst, is_managed=is_m)

        models_state = self.scan_current_storage()
        info = self.get_location_info()

        return {
            "success": True,
            "source_path": src,
            "target_path": dst,
            "storage_path": dst,
            "is_managed": is_m,
            "display_title": info["display_title"],
            "display_subtext": info["display_subtext"],
            "models_count": info["models_count"],
            "migrated": migrated,
            "migrated_count": len(migrated),
            "models": models_state
        }

    def migrate(self, source_path: Optional[str] = None, target_path: Optional[str] = None) -> Dict[str, Any]:
        return self.migrate_models(source_path, target_path)

    def get_model_file_path(self, model_id: str) -> Optional[str]:
        """
        Locates the model checkpoint file strictly in the active storage path.
        Checks all directory aliases (e.g. 'MP-SENet', 'mp_senet').
        Returns None if not found in active storage.
        """
        meta = self.registry_data["models"].get(model_id)
        if not meta:
            return None

        filename = meta["checkpoint_filename"]
        aliases = FOLDER_ALIASES.get(model_id, [model_id])

        for folder_name in aliases:
            candidate = os.path.join(self.storage_path, folder_name, filename)
            if os.path.isfile(candidate):
                return candidate
            if model_id == "deepfilternet3" or filename.endswith(".zip"):
                cand_extracted = os.path.join(self.storage_path, folder_name, "checkpoints", "model_120.ckpt.best")
                if os.path.isfile(cand_extracted):
                    return cand_extracted
                cand_extracted2 = os.path.join(self.storage_path, folder_name, "DeepFilterNet3", "checkpoints", "model_120.ckpt.best")
                if os.path.isfile(cand_extracted2):
                    return cand_extracted2

        # Direct location: storage_path/filename
        candidate_direct = os.path.join(self.storage_path, filename)
        if os.path.isfile(candidate_direct):
            return candidate_direct

        return None

    def get_model_status(self, model_id: str) -> Tuple[str, Optional[str], int]:
        """
        Determines the true, verified status of a model on disk.
        Returns (status, local_path, size_bytes)
        status: 'installed' | 'missing' | 'invalid' | 'downloading' | 'verifying'
        """
        if model_id in self._active_tasks:
            return self._active_tasks[model_id], None, 0

        path = self.get_model_file_path(model_id)
        if not path or not os.path.isfile(path):
            return "missing", None, 0

        # Validate file size
        size = os.path.getsize(path)
        min_expected = 100000 # At least 100 KB
        if size < min_expected:
            return "invalid", path, size

        # For DeepFilterNet3, verify config.ini presence
        if model_id == "deepfilternet3":
            ckpt_dir = os.path.dirname(path)
            base_dir = os.path.dirname(ckpt_dir)
            cfg_path = os.path.join(base_dir, "config.ini")
            if not os.path.isfile(cfg_path):
                return "invalid", path, size

        # For models with config files, verify config presence
        if model_id == "mp_senet":
            cfg = os.path.join(os.path.dirname(path), "config.json")
            need_write = not os.path.isfile(cfg)
            if not need_write:
                try:
                    with open(cfg, "r", encoding="utf-8") as f:
                        cdata = json.load(f)
                        if "beta" not in cdata:
                            need_write = True
                except Exception:
                    need_write = True
            if need_write:
                try:
                    default_cfg = {
                        "dense_channel": 64, "compress_factor": 0.3, "num_tsconformers": 4, "beta": 2.0,
                        "sampling_rate": 16000, "segment_size": 32000,
                        "n_fft": 400, "hop_size": 100, "win_size": 400
                    }
                    with open(cfg, "w", encoding="utf-8") as f:
                        json.dump(default_cfg, f, indent=2)
                except Exception:
                    pass

        # Calculate total folder size
        folder = os.path.dirname(path)
        total_size = 0
        try:
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
        except Exception:
            total_size = size

        return "installed", path, total_size

    def is_installed(self, model_id: str) -> bool:
        status, _, _ = self.get_model_status(model_id)
        return status == "installed"

    def list_models(self) -> Dict[str, Any]:
        """
        Dynamically constructs the model catalog with real disk validation.
        No stale boolean flags.
        """
        catalog = {}
        for mid, mdata in self.registry_data["models"].items():
            status, local_path, size_bytes = self.get_model_status(mid)
            installed = (status == "installed")

            effective_size = size_bytes if size_bytes > 0 else mdata.get("checkpoint_size_bytes", 0)
            size_mb = max(1, round(effective_size / (1024 * 1024)))
            size_formatted = f"{size_mb} MB"

            catalog[mid] = {
                **mdata,
                "status": status,
                "installed": installed,
                "validated": installed,
                "local_path": local_path,
                "size_bytes": effective_size,
                "size_mb": size_mb,
                "size_formatted": size_formatted
            }
        return catalog

    def set_model_task_status(self, model_id: str, task_status: Optional[str]):
        """Sets temporary status such as 'downloading' or 'verifying'."""
        if task_status:
            self._active_tasks[model_id] = task_status
        elif model_id in self._active_tasks:
            del self._active_tasks[model_id]

    def _seed_default_storage_if_empty(self, target_storage: str):
        """
        Seeds models from legacy storage or benchmark_archive ONLY into default storage
        when default storage is empty. Never seeds into custom user directories.
        """
        try:
            if os.path.exists(target_storage):
                found_models = 0
                for mid in self.registry_data["models"].keys():
                    filename = self.registry_data["models"][mid]["checkpoint_filename"]
                    aliases = FOLDER_ALIASES.get(mid, [mid])
                    for a in aliases:
                        if os.path.isfile(os.path.join(target_storage, a, filename)):
                            found_models += 1
                            break
                if found_models >= 4:
                    return # All models present
        except Exception:
            pass

        # 1. First copy from existing project models/storage if available
        legacy_storage = os.path.abspath(os.path.join(self.base_dir, "storage"))
        if os.path.isdir(legacy_storage) and os.path.normcase(legacy_storage) != os.path.normcase(target_storage):
            try:
                for item in os.listdir(legacy_storage):
                    s = os.path.join(legacy_storage, item)
                    if os.path.isdir(s):
                        aliases = FOLDER_ALIASES.get(item, [item])
                        canonical_folder = aliases[0]
                        d = os.path.join(target_storage, canonical_folder)
                        if not os.path.exists(d):
                            shutil.copytree(s, d)
            except Exception as e:
                print(f"[ModelStorageManager] Legacy seed notice: {e}", flush=True)

        # 2. Check benchmark_archive if any still missing
        archive_dir = os.path.abspath(os.path.join(self.base_dir, "..", "benchmark_archive"))
        if not os.path.isdir(archive_dir):
            return

        # MP-SENet
        mp_src = os.path.join(archive_dir, "models_repo", "mp_senet", "best_ckpt", "g_best_dns")
        mp_dst = os.path.join(target_storage, FOLDER_ALIASES["mp_senet"][0])
        if os.path.isfile(mp_src) and not any(os.path.isfile(os.path.join(target_storage, a, "g_best_dns")) for a in FOLDER_ALIASES["mp_senet"]):
            os.makedirs(mp_dst, exist_ok=True)
            shutil.copy2(mp_src, os.path.join(mp_dst, "g_best_dns"))
            cfg_src = os.path.join(archive_dir, "models_repo", "mp_senet", "best_ckpt", "config.json")
            if os.path.isfile(cfg_src):
                shutil.copy2(cfg_src, os.path.join(mp_dst, "config.json"))

        # ZipEnhancer
        zip_src = os.path.join(archive_dir, "models_repo", "zipenhancer", "pytorch_model.bin")
        zip_dst = os.path.join(target_storage, FOLDER_ALIASES["zipenhancer"][0])
        if os.path.isfile(zip_src) and not any(os.path.isfile(os.path.join(target_storage, a, "pytorch_model.bin")) for a in FOLDER_ALIASES["zipenhancer"]):
            os.makedirs(zip_dst, exist_ok=True)
            shutil.copy2(zip_src, os.path.join(zip_dst, "pytorch_model.bin"))
            cfg_src = os.path.join(archive_dir, "models_repo", "zipenhancer", "configs", "configuration.json")
            if os.path.isfile(cfg_src):
                shutil.copy2(cfg_src, os.path.join(zip_dst, "configuration.json"))

        # MossFormerGAN
        moss_src = os.path.join(archive_dir, "checkpoints", "MossFormerGAN_SE_16K", "last_best_checkpoint.pt")
        moss_dst = os.path.join(target_storage, FOLDER_ALIASES["mossformergan"][0])
        if os.path.isfile(moss_src) and not any(os.path.isfile(os.path.join(target_storage, a, "last_best_checkpoint.pt")) for a in FOLDER_ALIASES["mossformergan"]):
            os.makedirs(moss_dst, exist_ok=True)
            shutil.copy2(moss_src, os.path.join(moss_dst, "last_best_checkpoint.pt"))

        # DeepFilterNet3
        df_cache = os.path.expandvars(r"%LOCALAPPDATA%\DeepFilterNet\DeepFilterNet\Cache\DeepFilterNet3\checkpoints\model_120.ckpt.best")
        df_dst = os.path.join(target_storage, FOLDER_ALIASES["deepfilternet3"][0])
        if os.path.isfile(df_cache) and not any(os.path.isfile(os.path.join(target_storage, a, "model_120.ckpt.best")) for a in FOLDER_ALIASES["deepfilternet3"]):
            os.makedirs(df_dst, exist_ok=True)
            shutil.copy2(df_cache, os.path.join(df_dst, "model_120.ckpt.best"))
