"""Mock MLX partagé pour les tests — compatible isinstance() et import.

Utilisation dans chaque fichier de test :
    from tests.mocks.mlx import patch_mlx, MockMXArray
    patch_mlx()  # avant tout import du module sous test

Évite les conflits entre mocks sys.modules de différents fichiers de test.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock


class MockMXArray:
    """Proxy pour mx.array — compatible isinstance() et opérations arithmétiques."""
    def __init__(self, data=None, dtype="float16", ndim=3, shape=None):
        self._data = data if data is not None else 0.5
        self.dtype = dtype
        self.ndim = ndim
        self.shape = shape if shape else (8, 64, 64)
        self.size = 1
        for s in self.shape:
            self.size *= s
        self.T = self

    def astype(self, dtype):
        return MockMXArray(self._data, dtype, self.ndim, self.shape)

    def __sub__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __mul__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __add__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __truediv__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __rmul__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __radd__(self, other):
        return MockMXArray(0.0, "float16", 0, (1,))
    def __getitem__(self, key):
        new_shape = list(self.shape)
        if isinstance(key, tuple):
            for i, s in enumerate(key):
                if isinstance(s, slice):
                    start = s.start or 0
                    stop = s.stop or self.shape[i]
                    new_shape[i] = (stop - start) // (s.step or 1)
        return MockMXArray(self._data, self.dtype, self.ndim, tuple(new_shape))


def _build_core_module():
    """Construit un module mlx.core factice."""
    core = ModuleType("mlx.core")
    core.array = MockMXArray
    core.float16 = "float16"
    core.float32 = "float32"
    core.bfloat16 = "bfloat16"
    core.uint8 = "uint8"
    core.int8 = "int8"
    core.min = staticmethod(lambda x, axis=None, keepdims=False: MockMXArray(0.0, "float16", 0, (1,)))
    core.max = staticmethod(lambda x, axis=None, keepdims=False: MockMXArray(1.0, "float16", 0, (1,)))
    core.round = staticmethod(lambda x: x)
    core.clip = staticmethod(lambda x, a, b: x)
    core.maximum = staticmethod(lambda a, b: a)
    core.expand_dims = staticmethod(lambda x, axis: x)
    core.concatenate = staticmethod(lambda arrays, axis: arrays[0])
    return core


def patch_mlx():
    """Patche sys.modules avec des mocks compatibles mlx.core.

    À appeler AVANT tout import du module sous test.
    """
    mock_mlx = ModuleType("mlx")
    mock_core = _build_core_module()
    mock_mlx.core = mock_core

    # Sous-module metal
    mock_metal = ModuleType("mlx.metal")
    mock_metal.is_available = MagicMock(return_value=False)
    mock_mlx.metal = mock_metal

    # Injection propre — écraser les entrées existantes
    if "mlx" in sys.modules:
        # Préserver les références existantes pour éviter les warnings
        pass
    sys.modules["mlx"] = mock_mlx
    sys.modules["mlx.core"] = mock_core
    sys.modules["mlx.metal"] = mock_metal

    # Nettoyer tout cache d'import qui pointerait vers les anciens modules
    for key in list(sys.modules.keys()):
        if key.startswith("src.cache.kv_compress") or key.startswith("tests.test_kv_compress"):
            del sys.modules[key]


def patch_mlx_lm():
    """Patche sys.modules pour mlx_lm (utilisé par test_lora_adapter)."""
    import unittest
    from unittest.mock import MagicMock

    mock_lm = ModuleType("mlx_lm")
    mock_utils = ModuleType("mlx_lm.utils")
    mock_sample = ModuleType("mlx_lm.sample_utils")

    mock_lm.load = MagicMock(return_value=(MagicMock(), MagicMock()))
    mock_lm.stream_generate = MagicMock()
    mock_lm.utils = mock_utils
    mock_lm.sample_utils = mock_sample
    mock_utils.load_adapters = MagicMock(return_value=MagicMock())
    mock_sample.make_sampler = MagicMock()
    mock_sample.make_repetition_penalty = MagicMock()
    mock_sample.make_logits_processors = MagicMock()

    sys.modules["mlx_lm"] = mock_lm
    sys.modules["mlx_lm.utils"] = mock_utils
    sys.modules["mlx_lm.sample_utils"] = mock_sample
