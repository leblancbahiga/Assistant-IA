"""Tests pour KV Cache Compression style MLA (Item 42, P2 #74).

V15 Phase 5 — Compression du KV cache par quantification int8 + fenêtrage.
"""

import pytest
from unittest.mock import patch, MagicMock

# Patch MLX avant tout import du module sous test
from tests.mocks.mlx import patch_mlx, MockMXArray
patch_mlx()

from src.cache.kv_compress import (
    quantize_kv_cache,
    dequantize_kv_cache,
    window_kv_cache,
    compression_stats,
    _dtype_bytes as dtype_bytes,
    _find_seq_dim as find_seq_dim,
)


# ─── dtype_bytes ─────────────────────────────────────────────────────


class TestDtypeBytes:
    def test_float16(self):
        assert dtype_bytes("float16") == 2

    def test_float32(self):
        assert dtype_bytes("float32") == 4

    def test_uint8(self):
        assert dtype_bytes("uint8") == 1

    def test_unknown_fallback(self):
        assert dtype_bytes("bfloat16") == 2  # fallback


# ─── find_seq_dim ────────────────────────────────────────────────────


class TestFindSeqDim:
    def test_2d_tensor(self):
        # [num_heads, seq_len]
        t = MockMXArray(0.5, "float16", 2, (8, 64))
        assert find_seq_dim(t) == 1

    def test_3d_tensor(self):
        # [heads, seq_len, head_dim] → seq_dim = 1
        t = MockMXArray(0.5, "float16", 3, (8, 64, 128))
        assert find_seq_dim(t) == 1

    def test_4d_tensor(self):
        # [layers, heads, seq_len, head_dim] → seq_dim = 2
        t = MockMXArray(0.5, "float16", 4, (16, 4, 64, 128))
        assert find_seq_dim(t) == 2

    def test_1d_tensor(self):
        t = MockMXArray(0.5, "float16", 1, (512,))
        assert find_seq_dim(t) is None


# ─── quantize_kv_cache ──────────────────────────────────────────────


class TestQuantize:
    def test_quantize_fp16_tensor(self):
        data = {"key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128))}
        result = quantize_kv_cache(data)
        assert "key_cache" in result
        assert f"key_cache_scale" in result

    def test_skip_non_float_tensor(self):
        data = {"key_cache": MockMXArray(128, "uint8", 4, (8, 4, 64, 128))}
        result = quantize_kv_cache(data)
        assert result["key_cache"].dtype == "uint8"

    def test_empty_dict(self):
        assert quantize_kv_cache({}) == {}

    def test_preserves_non_tensor(self):
        data = {"metadata": {"layer": 0}}
        result = quantize_kv_cache(data)
        assert result["metadata"] == {"layer": 0}


# ─── dequantize_kv_cache ────────────────────────────────────────────

class TestDequantize:
    def test_dequantize_uint8_tensor(self):
        """Quantification → déquantification round-trip."""
        orig_data = {"key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128))}
        q = quantize_kv_cache(orig_data)
        assert "key_cache_scale" in q
        assert "key_cache_min" in q

        # Simuler le chargement (type uint8 pour le tenseur principal)
        q_loaded = {
            "key_cache": MockMXArray(128, "uint8", 4, (8, 4, 64, 128)),
            "key_cache_scale": MockMXArray(0.01, "float16", 0, (1,)),
            "key_cache_min": MockMXArray(-1.0, "float16", 0, (1,)),
        }
        result = dequantize_kv_cache(q_loaded)
        assert "key_cache" in result
        assert result["key_cache"].dtype == "float16"
        assert "key_cache_scale" not in result
        assert "key_cache_min" not in result

    def test_passthrough_fp16(self):
        """Un tenseur flottant non quantifié passe tel quel."""
        data = {"key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128))}
        result = dequantize_kv_cache(data)
        assert "key_cache" in result
        assert result["key_cache"].dtype == "float16"

    def test_empty_dict(self):
        assert dequantize_kv_cache({}) == {}

    def test_partial_metadata(self):
        """Scale sans min → pas déquantifié, métadonnée orpheline préservée."""
        data = {
            "key_cache": MockMXArray(128, "uint8", 4, (8, 4, 64, 128)),
            "key_cache_scale": MockMXArray(0.01, "float16", 0, (1,)),
        }
        result = dequantize_kv_cache(data)
        # Les deux clés sont préservées car impossible de déquantifier sans min
        assert "key_cache_scale" in result


# ─── window_kv_cache ──────────────────────────────────────────────


class TestWindow:
    def test_smaller_than_max(self):
        """Séquence plus petite que le max → pas de coupure."""
        data = {
            "key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128)),
            "value_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128)),
        }
        result = window_kv_cache(data, max_tokens=256)
        assert len(result) == 2
        assert "key_cache" in result

    def test_larger_than_max(self):
        """Séquence plus grande → fenêtrage appliqué."""
        data = {
            "key_cache": MockMXArray(128, "float16", 4, (8, 4, 256, 128)),
            "value_cache": MockMXArray(128, "float16", 4, (8, 4, 256, 128)),
        }
        result = window_kv_cache(data, max_tokens=128, system_prompt_tokens=32)
        assert "key_cache" in result

    def test_1d_tensor_passthrough(self):
        """Tenseur 1D (embedding) non fenêtré."""
        data = {"embed": MockMXArray(128, "float16", 1, (512,))}
        result = window_kv_cache(data, max_tokens=128)
        assert "embed" in result

    def test_mixed_data(self):
        """Mélange tenseurs 4D, dict, scalaires."""
        data = {
            "key_cache": MockMXArray(128, "float16", 4, (8, 4, 300, 128)),
            "metadata": {"num_layers": 16},
            "temperature": 0.7,
        }
        result = window_kv_cache(data, max_tokens=128, system_prompt_tokens=64)
        assert "key_cache" in result
        assert result["metadata"] == {"num_layers": 16}
        assert result["temperature"] == 0.7


# ─── compression_stats ──────────────────────────────────────────────


class TestCompressionStats:
    def test_fp16_tensor(self):
        data = {"key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128))}
        stats = compression_stats(data)
        assert "original_bytes" in stats
        assert "compressed_bytes" in stats
        assert stats["original_bytes"] >= stats["compressed_bytes"]

    def test_already_uint8(self):
        data = {"key_cache": MockMXArray(128, "uint8", 4, (8, 4, 64, 128))}
        stats = compression_stats(data)
        assert stats["original_bytes"] == stats["compressed_bytes"]

    def test_empty_dict(self):
        stats = compression_stats({})
        assert stats["tensors"] == 0
        assert stats["original_bytes"] == 0

    def test_skips_metadata(self):
        """Les métadonnées _scale/_min sont exclues."""
        data = {
            "key_cache": MockMXArray(128, "float16", 4, (8, 4, 64, 128)),
            "key_cache_scale": MockMXArray(0.01, "float16", 0, (1,)),
        }
        stats = compression_stats(data)
        assert stats["tensors"] == 1  # un seul tenseur compté
