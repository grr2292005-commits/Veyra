import threading
from typing import Dict, Any, Optional
from .base_adapter import BaseModelAdapter
from .mp_senet_adapter import MPSENetAdapter
from .zipenhancer_adapter import ZipEnhancerAdapter
from .mossformergan_adapter import MossFormerGANAdapter
from .deepfilternet_adapter import DeepFilterNetAdapter

ADAPTER_MAP = {
    "mp_senet": MPSENetAdapter,
    "zipenhancer": ZipEnhancerAdapter,
    "mossformergan": MossFormerGANAdapter,
    "deepfilternet3": DeepFilterNetAdapter,
}

class ModelFactory:
    """
    Creates and manages active model adapter instances with thread-safe concurrency protection.
    """
    _active_adapter: Optional[BaseModelAdapter] = None
    _active_model_id: Optional[str] = None
    _factory_lock = threading.Lock()

    @classmethod
    def create_adapter(
        cls,
        model_id: str,
        checkpoint_path: str,
        device: Optional[str] = None
    ) -> BaseModelAdapter:
        from models.manager import ModelManager
        mgr = ModelManager()
        model_meta = mgr.registry_data["models"].get(model_id, {})
        return cls.get_adapter(model_id, model_meta, checkpoint_path, device=device)

    @classmethod
    def get_adapter(
        cls,
        model_id: str,
        model_meta: Dict[str, Any],
        checkpoint_path: str,
        device: Optional[str] = None
    ) -> BaseModelAdapter:
        with cls._factory_lock:
            # Check if device changed (e.g. from GPU to CPU)
            device_matches = True
            if cls._active_adapter is not None and device is not None:
                active_dev_str = str(getattr(cls._active_adapter, "device", "")).lower()
                req_dev_str = str(device).lower()
                if req_dev_str == "cpu" and "cpu" not in active_dev_str:
                    device_matches = False
                elif req_dev_str in ("cuda", "gpu") and "cuda" not in active_dev_str:
                    device_matches = False

            # Reuse already initialized adapter if identical model and device
            if cls._active_model_id == model_id and cls._active_adapter is not None and device_matches:
                if cls._active_adapter.is_initialized():
                    return cls._active_adapter

            # Cleanup old adapter to free GPU memory before loading new one
            if cls._active_adapter is not None:
                cls._active_adapter.cleanup()
                cls._active_adapter = None
                cls._active_model_id = None

            adapter_cls = ADAPTER_MAP.get(model_id)
            if not adapter_cls:
                raise ValueError(f"No adapter registered for model ID: {model_id}")

            adapter = adapter_cls(model_id, model_meta)
            adapter.initialize(checkpoint_path, device=device)

            cls._active_adapter = adapter
            cls._active_model_id = model_id
            return adapter

    @classmethod
    def cleanup_all(cls):
        with cls._factory_lock:
            if cls._active_adapter is not None:
                cls._active_adapter.cleanup()
                cls._active_adapter = None
                cls._active_model_id = None
