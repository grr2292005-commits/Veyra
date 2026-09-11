import os
import sys
import platform
import psutil
from typing import Dict, Any, List, Optional

class HardwareManager:
    """
    Authoritative Hardware & Inference Capability Service.
    Inspects host CPU, RAM, and performs runtime validation of PyTorch CUDA backends.
    """
    def __init__(self):
        self._cached_profile = None
        self._cached_gpus = None

    def detect_cpu(self) -> Dict[str, Any]:
        cpu_name = platform.processor() or "Unknown CPU"
        # On Windows, read directly from registry (instant, 0 child processes, 0 console windows)
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                reg_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
                if reg_name and reg_name.strip():
                    cpu_name = reg_name.strip()
            except Exception:
                pass

        cores_phys = psutil.cpu_count(logical=False) or 4
        cores_log = psutil.cpu_count(logical=True) or 8
        return {
            "name": cpu_name,
            "physical_cores": cores_phys,
            "logical_cores": cores_log,
            "usage_percent": psutil.cpu_percent(interval=None)
        }

    def detect_ram(self) -> Dict[str, Any]:
        ram = psutil.virtual_memory()
        return {
            "total_gb": round(ram.total / (1024 ** 3), 1),
            "available_gb": round(ram.available / (1024 ** 3), 1),
            "used_percent": ram.percent
        }

    def detect_cuda(self) -> bool:
        """Lightweight runtime verification that PyTorch can actually execute on CUDA."""
        gpus = self.detect_gpus()
        return any(g.get("cuda") for g in gpus)

    def detect_gpus(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Detects available GPUs and verifies their actual CUDA inference viability.
        """
        if self._cached_gpus is not None and not refresh:
            return self._cached_gpus

        gpus = []
        try:
            import torch
            if torch.cuda.is_available():
                for idx in range(torch.cuda.device_count()):
                    name = torch.cuda.get_device_name(idx)
                    mem_props = torch.cuda.get_device_properties(idx)
                    vram_total_mb = round(mem_props.total_memory / (1024 ** 2), 1)
                    try:
                        free_b, _ = torch.cuda.mem_get_info(idx)
                        vram_free_mb = round(free_b / (1024 ** 2), 1)
                    except Exception:
                        vram_free_mb = vram_total_mb

                    total_gb = round(vram_total_mb / 1024.0, 1)
                    free_gb = round(vram_free_mb / 1024.0, 1)

                    # Verify actual CUDA usability
                    cuda_viable = False
                    try:
                        t = torch.zeros((1,), device=f"cuda:{idx}")
                        del t
                        cuda_viable = True
                    except Exception:
                        pass

                    gpus.append({
                        "id": f"cuda:{idx}",
                        "index": idx,
                        "name": name,
                        "device_name": name,
                        "vramGB": total_gb,
                        "total_vram_gb": total_gb,
                        "free_vram_gb": free_gb,
                        "vram_total_mb": vram_total_mb,
                        "vram_free_mb": vram_free_mb,
                        "cuda": cuda_viable,
                        "cuda_available": cuda_viable,
                        "available": cuda_viable
                    })
        except Exception:
            pass

        self._cached_gpus = gpus
        return gpus

    def detect_gpu(self) -> Dict[str, Any]:
        """Returns primary GPU dictionary or fallback CPU representation."""
        gpus = self.detect_gpus()
        if gpus:
            return gpus[0]
        return {
            "available": False,
            "cuda_available": False,
            "cuda": False,
            "device_name": "None",
            "name": "None",
            "total_vram_gb": 0.0,
            "free_vram_gb": 0.0,
            "vramGB": 0.0,
            "vram_total_mb": 0.0,
            "vram_free_mb": 0.0,
            "driver_version": "N/A"
        }

    def get_supported_backends(self) -> Dict[str, bool]:
        has_cuda = self.detect_cuda()
        return {
            "cpu": True,
            "cuda": has_cuda
        }

    def get_recommended_device(self) -> str:
        return "cuda" if self.detect_cuda() else "cpu"

    def resolve_device(self, req_dev: str = "auto") -> str:
        """
        Resolves device selection ('auto', 'cuda', 'cuda:0', 'cpu') to a concrete PyTorch device string.
        """
        req = (req_dev or "auto").strip().lower()
        if req == "cpu":
            return "cpu"
        if req in ("cuda", "gpu") or req.startswith("cuda"):
            if self.detect_cuda():
                return req if req.startswith("cuda:") else "cuda:0"
            return "cpu"
        # auto
        return "cuda:0" if self.detect_cuda() else "cpu"

    def get_available_devices(self) -> List[Dict[str, Any]]:
        devices = [
            {
                "id": "auto",
                "name": "Automatic (Recommended)",
                "label": "Automatic (Recommended)",
                "type": "auto",
                "available": True
            }
        ]
        gpus = self.detect_gpus()
        for g in gpus:
            if g.get("cuda"):
                clean_name = g["name"].replace("NVIDIA GeForce ", "NVIDIA ").replace(" Laptop GPU", "")
                vram_gb = int(round(g.get("total_vram_gb", 6.0)))
                label = f"GPU — {clean_name} ({vram_gb} GB VRAM)"
                devices.append({
                    "id": g["id"],
                    "device_str": g["id"],
                    "name": label,
                    "label": label,
                    "type": "cuda",
                    "available": True,
                    "vramGB": vram_gb,
                    "vram_gb": float(vram_gb)
                })
        devices.append({
            "id": "cpu",
            "name": "CPU — System Processor",
            "label": "CPU — System Processor",
            "type": "cpu",
            "available": True
        })
        return devices

    def _classify_hardware(self, gpu_info: Dict[str, Any], ram_info: Dict[str, Any]) -> Dict[str, Any]:
        has_cuda = gpu_info.get("available", False) or gpu_info.get("cuda_available", False)
        vram_mb = gpu_info.get("vram_total_mb", 0.0) or (gpu_info.get("total_vram_gb", 0.0) * 1024.0)

        if has_cuda and vram_mb >= 7500:
            return {
                "tier": "A",
                "tier_name": "Performance GPU (8GB+ VRAM)",
                "recommended_model": "mp_senet",
                "warnings": {}
            }
        elif has_cuda and vram_mb >= 3500:
            return {
                "tier": "B",
                "tier_name": "Entry Dedicated GPU (4–6GB VRAM)",
                "recommended_model": "mp_senet",
                "warnings": {
                    "mossformergan": "Requires ~4.5 GB VRAM. Running on a 4-6GB GPU may approach system display memory limits."
                }
            }
        elif has_cuda and vram_mb >= 1800:
            return {
                "tier": "C",
                "tier_name": "Low VRAM GPU (2-4GB)",
                "recommended_model": "zipenhancer",
                "warnings": {
                    "mossformergan": "Not recommended due to VRAM limits.",
                    "mp_senet": "May experience high VRAM pressure; use 1.0s window."
                }
            }
        else:
            return {
                "tier": "D",
                "tier_name": "CPU / Integrated Graphics",
                "recommended_model": "deepfilternet3",
                "warnings": {
                    "mossformergan": "Not recommended without a dedicated GPU.",
                    "mp_senet": "Will run in CPU mode; processing may be slower.",
                    "zipenhancer": "Will run in CPU mode; processing may be slower."
                }
            }

    def get_profile(self, refresh: bool = False) -> Dict[str, Any]:
        if self._cached_profile and not refresh:
            return self._cached_profile

        cpu_info = self.detect_cpu()
        ram_info = self.detect_ram()
        gpus = self.detect_gpus()
        primary_gpu = gpus[0] if gpus else self.detect_gpu()
        tier_info = self._classify_hardware(primary_gpu, ram_info)
        backends = self.get_supported_backends()
        recommended_dev = self.get_recommended_device()
        available_devs = self.get_available_devices()

        profile = {
            "os": f"{platform.system()} {platform.release()} ({platform.architecture()[0]})",
            "cpu": cpu_info,
            "ram": ram_info,
            "ramGB": int(round(ram_info["total_gb"])),
            "gpus": gpus,
            "gpu": primary_gpu,
            "backends": backends,
            "available_devices": available_devs,
            "recommendedDevice": recommended_dev,
            "tier": tier_info["tier"],
            "recommended_tier": tier_info["tier"],
            "tier_name": tier_info["tier_name"],
            "recommended_model": tier_info["recommended_model"],
            "model_warnings": tier_info["warnings"]
        }

        self._cached_profile = profile
        return profile

# Backwards compatibility alias
HardwareDetector = HardwareManager

if __name__ == "__main__":
    manager = HardwareManager()
    prof = manager.get_profile()
    import json
    print(json.dumps(prof, indent=2))
