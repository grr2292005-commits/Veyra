import os
import sys
import shutil
import tempfile
import socket
import contextlib
from typing import Generator, Dict, Any, Optional

try:
    import psutil
except ImportError:
    psutil = None

try:
    import torch
except ImportError:
    torch = None

class TestHelpers:
    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Returns current process RAM and GPU VRAM if available."""
        mem = {"ram_mb": 0.0, "vram_mb": 0.0}
        if psutil:
            proc = psutil.Process(os.getpid())
            mem["ram_mb"] = round(proc.memory_info().rss / (1024 * 1024), 2)
        if torch and torch.cuda.is_available():
            mem["vram_mb"] = round(torch.cuda.memory_allocated() / (1024 * 1024), 2)
            mem["vram_reserved_mb"] = round(torch.cuda.memory_reserved() / (1024 * 1024), 2)
        return mem

    @staticmethod
    def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    @staticmethod
    def find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

    @staticmethod
    @contextlib.contextmanager
    def temp_directory(prefix: str = "sp_test_") -> Generator[str, None, None]:
        d = tempfile.mkdtemp(prefix=prefix)
        try:
            yield os.path.abspath(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @staticmethod
    def create_dummy_checkpoint(path: str, size_bytes: int = 1024 * 1024):
        """Creates a dummy checkpoint file of specified size."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"0" * size_bytes)
