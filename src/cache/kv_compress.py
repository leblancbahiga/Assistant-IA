"""NURU V15 Phase 5 — KV Cache Compression (Item 42, P2 #74).

Compression du KV cache MLX en mémoire et sur disque :

1. Quantification int8 — fp16 → uint8 par token (÷2 RAM, ÷2 stockage)
2. Fenêtrage contextuel — keep max N tokens récents (contrôle mémoire borné)
3. Intégration transparente dans KVPersistentCache

Principe :
  - Chaque tenseur K/V est quantifié token-par-token (scale + zero_point par token)
  - Déquantification automatique au restore (transparent pour le modèle)
  - Fenêtrage : seuls les max_tokens récents + system prompt sont conservés

Économie estimée sur M1 8 Go :
  - Cache 512 tokens → ~40-80 MB (int8) vs ~80-160 MB (fp16)
  - Cache 2048 tokens → ~160-320 MB (int8) vs ~320-640 MB (fp16)
  - Soit ~50% RAM immédiat, jusqu'à 75% avec fenêtrage agressif
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Quantification int8 ─────────────────────────────────────────────


def quantize_kv_cache(kv_data: dict, per_token: bool = True) -> dict:
    """Quantifie un dict de tenseurs KV de fp16 vers uint8.

    Args:
        kv_data: dict {layer_key: mx.array} — tenseurs float16
        per_token: si True, quantifie token-par-token (meilleure précision)

    Returns:
        dict avec tenseurs uint8 + métadonnées _scale / _zp

    Note technique :
        La quantification per-token ajoute scale+zp par token (2 floats/head),
        soit ~8 bytes/token/head — négligeable devant le gain 2x.
    """
    import mlx.core as mx

    result = {}
    for key, tensor in kv_data.items():
        if not isinstance(tensor, mx.array):
            result[key] = tensor
            continue

        # Ne quantifier que les tenseurs float16 (les métadonnées passent)
        if tensor.dtype not in (mx.float16, mx.float32, mx.bfloat16):
            result[key] = tensor
            continue

        if per_token and tensor.ndim >= 2:
            # Quantification per-token : chaque token (dim -1) a son scale/zp
            # tensor shape: [..., seq_len, head_dim]
            # On quantifie le long de head_dim (dernière dimension)
            min_val = mx.min(tensor, axis=-1, keepdims=True)  # [..., seq_len, 1]
            max_val = mx.max(tensor, axis=-1, keepdims=True)
        else:
            # Quantification globale : un seul scale pour tout le tenseur
            min_val = mx.min(tensor)
            max_val = mx.max(tensor)

        scale = (max_val - min_val) / 255.0
        # Éviter scale=0 (tenseur uniforme)
        scale = mx.maximum(scale, 1e-10)

        quantized = mx.round((tensor - min_val) / scale)
        quantized = mx.clip(quantized, 0, 255).astype(mx.uint8)

        result[key] = quantized
        result[f"{key}_scale"] = scale.astype(mx.float16)
        result[f"{key}_min"] = min_val.astype(mx.float16)

    return result


def dequantize_kv_cache(kv_data: dict) -> dict:
    """Déquantifie les tenseurs uint8 vers fp16.

    Cherche les paires (tenseur, _scale, _min) et reconstruit fp16.
    Les tenseurs déjà en float passent inchangés.
    """
    import mlx.core as mx

    result = {}
    # Index des métadonnées de quantification
    consumed_keys = set()

    # Identifier les paires tenseur + métadonnées
    quantized_keys = set()
    for key in kv_data:
        if key.endswith("_scale") or key.endswith("_min"):
            base = key.rsplit("_", 1)[0]
            if base in kv_data:
                quantized_keys.add(base)
            else:
                # Métadonnées orphelines — les garder dans le résultat
                consumed_keys.discard(key)  # ne pas consommer
        else:
            # Voir si c'est un tenseur quantifié avec les deux métadonnées
            scale_key = f"{key}_scale"
            min_key = f"{key}_min"
            if scale_key in kv_data and min_key in kv_data:
                consumed_keys.add(scale_key)
                consumed_keys.add(min_key)

    for key, tensor in kv_data.items():
        scale_key = f"{key}_scale"
        min_key = f"{key}_min"

        if key in quantized_keys and scale_key in kv_data and min_key in kv_data:
            # Déquantifier
            quant = tensor.astype(mx.float32)
            scale = kv_data[scale_key].astype(mx.float32)
            min_val = kv_data[min_key].astype(mx.float32)

            # Broadcast si nécessaire
            if scale.ndim < quant.ndim:
                for _ in range(quant.ndim - scale.ndim):
                    scale = mx.expand_dims(scale, -1)
                    min_val = mx.expand_dims(min_val, -1)

            dequantized = quant * scale + min_val
            result[key] = dequantized.astype(mx.float16)
        elif key in consumed_keys:
            continue  # C'est une métadonnée utilisée, ne pas inclure
        else:
            # Pas quantifié ou métadonnée orpheline, laisser tel quel
            result[key] = tensor

    return result


# ─── Fenêtrage contextual ────────────────────────────────────────────


def window_kv_cache(
    kv_data: dict,
    max_tokens: int = 1024,
    system_prompt_tokens: int = 128,
) -> dict:
    """Tronque le KV cache pour ne garder que les max_tokens récents.

    Stratégie :
      1. Conserver le début du prompt (system prompt) ← system_prompt_tokens
      2. Conserver la fin (messages récents) ← max_tokens - system_prompt_tokens
      3. Éliminer le milieu (Lost-in-the-Middle zone)

    Args:
        kv_data: dict {key: mx.array}
        max_tokens: nombre max de tokens à conserver (total)
        system_prompt_tokens: nb de tokens system prompt à garder au début

    Returns:
        dict fenêtré, ou l'original si plus petit que max_tokens
    """
    import mlx.core as mx

    result = {}
    for key, tensor in kv_data.items():
        if not isinstance(tensor, mx.array) or tensor.ndim < 2:
            result[key] = tensor
            continue

        # Chercher la dimension séquence (généralement index -2)
        # shape typique : [heads, seq_len, head_dim]
        seq_dim = _find_seq_dim(tensor)

        if seq_dim is None:
            result[key] = tensor
            continue

        seq_len = tensor.shape[seq_dim]
        if seq_len <= max_tokens:
            result[key] = tensor
            continue

        # Fenêtrage : garder debut (system prompt) + fin (messages récents)
        keep_start = min(system_prompt_tokens, seq_len // 2)
        keep_end = max_tokens - keep_start

        # slices : garder les keep_start premiers + les keep_end derniers
        slices = [slice(None)] * tensor.ndim
        start_indices = list(range(seq_len))

        # Tokens à garder
        keep_indices = list(range(keep_start)) + list(range(seq_len - keep_end, seq_len))
        # Trier (pour garder l'ordre chronologique)
        keep_indices.sort()

        # Construire le tenseur fenêtré
        # Note : on ne peut pas fancy-index facilement en MLX
        # Approche : concaténer les deux parties
        slices_start = slices.copy()
        slices_start[seq_dim] = slice(0, keep_start)
        slice_start = tensor[tuple(slices_start)]

        slices_end = slices.copy()
        slices_end[seq_dim] = slice(seq_len - keep_end, seq_len)
        slice_end = tensor[tuple(slices_end)]

        windowed = mx.concatenate([slice_start, slice_end], axis=seq_dim)
        result[key] = windowed

    return result


def _find_seq_dim(tensor) -> Optional[int]:
    """Trouve la dimension qui contient la séquence (taille > head_dim)."""
    shape = tensor.shape
    if len(shape) < 2:
        return None
    # La dimension séquence est la plus grande après la première (heads)
    # shape = [heads, seq_len, head_dim] ou [n_layers, heads, seq_len, head_dim]
    # La dimension seq est typiquement la deuxième plus grande
    if len(shape) == 2:
        return 1  # [seq_len, dim]
    if len(shape) == 3:
        # [heads, seq_len, head_dim] → seq_len est généralement la plus variable
        return 1
    # 4D : [layers, heads, seq_len, head_dim]
    return 2


# ─── Test et stats ───────────────────────────────────────────────────


def compression_stats(kv_data: dict) -> dict:
    """Calcule les stats de compression d'un dict de tenseurs.

    Returns:
        dict avec stats de taille avant/après quantification
    """
    import mlx.core as mx

    total_bytes_orig = 0
    total_bytes_compressed = 0
    tensor_count = 0

    for key, tensor in kv_data.items():
        if not isinstance(tensor, mx.array):
            continue
        if key.endswith("_scale") or key.endswith("_min"):
            continue

        tensor_count += 1
        dtype_size = _dtype_bytes(tensor.dtype)
        total_bytes_orig += tensor.size * dtype_size

        # Simuler ce que donnerait la quantification
        if dtype_size > 1:  # Quantifiable
            total_bytes_compressed += tensor.size * 1  # uint8
            # Ajouter les métadonnées
            if tensor.ndim >= 2 and tensor.shape[-1] > 1:
                # per-token: 2 floats (scale + min) par token
                per_token_overhead = tensor.shape[-2] if tensor.ndim >= 2 else 0
                total_bytes_compressed += per_token_overhead * 4  # float32
        else:
            total_bytes_compressed += tensor.size * 1

    ratio = (total_bytes_compressed / total_bytes_orig * 100) if total_bytes_orig > 0 else 100

    return {
        "tensors": tensor_count,
        "original_bytes": total_bytes_orig,
        "original_mb": round(total_bytes_orig / (1024**2), 2),
        "compressed_bytes": total_bytes_compressed,
        "compressed_mb": round(total_bytes_compressed / (1024**2), 2),
        "compression_ratio_pct": round(ratio, 1),
        "savings_mb": round((total_bytes_orig - total_bytes_compressed) / (1024**2), 2),
    }


def _dtype_bytes(dtype) -> int:
    """Retourne la taille en octets d'un dtype MLX."""
    dtype_str = str(dtype)
    if "float16" in dtype_str or "bfloat16" in dtype_str:
        return 2
    if "float32" in dtype_str:
        return 4
    if "float64" in dtype_str:
        return 8
    if "uint8" in dtype_str or "int8" in dtype_str:
        return 1
    if "uint16" in dtype_str or "int16" in dtype_str:
        return 2
    if "uint32" in dtype_str or "int32" in dtype_str:
        return 4
    if "uint64" in dtype_str or "int64" in dtype_str:
        return 8
    return 2  # fallback
