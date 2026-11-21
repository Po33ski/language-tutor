"""Make CUDA 12 cuBLAS visible to CTranslate2 (the engine behind faster-whisper).

CTranslate2 wheels are built against CUDA 12 and load `libcublas.so.12` at runtime,
while PyTorch (used by Kokoro) ships CUDA 13 libraries. The `nvidia-cublas-cu12`
package provides the CUDA 12 libraries; loading them globally lets CTranslate2's later
`dlopen("libcublas.so.12")` find them without changing LD_LIBRARY_PATH.
"""

import ctypes
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_LIBRARIES = ("libcublasLt.so.12", "libcublas.so.12")
_loaded = False


def preload_cuda12_libraries() -> None:
    global _loaded
    if _loaded:
        return
    try:
        import nvidia.cublas  # type: ignore[import-not-found]
    except ImportError:
        logger.info("nvidia-cublas-cu12 not installed; Whisper will use system CUDA libraries")
        return
    lib_dir = Path(next(iter(nvidia.cublas.__path__))) / "lib"
    for name in _LIBRARIES:
        path = lib_dir / name
        if path.exists():
            ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
    _loaded = True
