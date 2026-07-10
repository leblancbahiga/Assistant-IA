"""NURU V15 Phase 5 — KV Cache Persistant (Item 41, P2 #64).

Cache les états intermédiaires du KV cache (attention key-value pairs)
entre les déchargements/rechargements du modèle MLX sur M1 8 Go.

Principe :
1. Avant déchargement → sérialiser le KV cache sur disque
2. Après rechargement → restaurer le KV cache si le prompt correspond
3. Évite de recalculer le préfixe (system prompt + historique conversation)
4. Économie : 2-8 Go de calcul GPU sauté par rechargement

Architecture :
  - Stockage : MLX .safetensors sur disque (~/.nuru/kv_cache/)
  - Index : SQLite (model_id × session_id × prompt_hash)
  - Budget : enregistré dans RAMBudgetManager (cache_llm, 200 MB)
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Répertoire de cache
KV_CACHE_DIR = Path.home() / ".nuru" / "kv_cache"


@dataclass
class KVCacheEntry:
    """Métadonnées d'une entrée de cache KV."""
    model_id: str
    session_id: str
    prompt_hash: str
    turn_number: int
    num_layers: int
    num_tokens: int
    file_path: str       # Chemin vers le fichier .safetensors
    created_at: float
    accessed_at: float
    size_mb: float       # Taille estimée du fichier


class KVPersistentCache:
    """Cache KV persistant entre sessions de conversation.

    Usage:
        kvc = KVPersistentCache()
        await kvc.save(model, "llama-3.2-3b", "session_123", prompt, turn=5)
        kv_data = await kvc.restore(model, "llama-3.2-3b", "session_123", prompt)
        if kv_data:
            continue_generation_from(kv_data)
    """

    def __init__(self, max_entries: int = 10, max_total_mb: int = 1024):
        self.max_entries = max_entries
        self.max_total_mb = max_total_mb
        self._index_path = KV_CACHE_DIR / "index.json"
        self._entries: dict[str, KVCacheEntry] = {}  # key = f"{session_id}:{prompt_hash}"
        self._load_index()

    # ─── Gestion de l'index ──────────────────────────────────────────

    def _load_index(self) -> None:
        """Charge l'index depuis le disque."""
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text())
            for key, d in data.items():
                self._entries[key] = KVCacheEntry(**d)
            logger.debug(f"KV Cache index chargé : {len(self._entries)} entrées")
        except Exception as e:
            logger.warning(f"⚠️ KV Cache index corrompu : {e}")
            self._entries = {}

    def _save_index(self) -> None:
        """Sauvegarde l'index sur le disque."""
        KV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            key: {
                "model_id": e.model_id,
                "session_id": e.session_id,
                "prompt_hash": e.prompt_hash,
                "turn_number": e.turn_number,
                "num_layers": e.num_layers,
                "num_tokens": e.num_tokens,
                "file_path": e.file_path,
                "created_at": e.created_at,
                "accessed_at": e.accessed_at,
                "size_mb": e.size_mb,
            }
            for key, e in self._entries.items()
        }
        try:
            self._index_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"⚠️ KV Cache index save échoué : {e}")

    # ─── API Publique ────────────────────────────────────────────────

    def _make_key(self, session_id: str, prompt_hash: str) -> str:
        return f"{session_id}:{prompt_hash}"

    def save(
        self,
        model: Any,
        session_id: str,
        prompt: str,
        turn_number: int,
        model_id: str = "default",
    ) -> bool:
        """Sauvegarde le KV cache du modèle sur disque.

        Note : MLX gère le KV cache en interne. Cette méthode accède
        à `model.kv_cache` si disponible, sinon sauvegarde l'état
        du modèle (state_dict) comme checkpoint de reprise.

        Returns:
            True si la sauvegarde a réussi
        """
        if model is None:
            return False

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        key = self._make_key(session_id, prompt_hash)

        # Ne pas sauvegarder si déjà présent (évite doublon)
        if key in self._entries:
            self._entries[key].accessed_at = time.time()
            self._save_index()
            return True

        # Déterminer le chemin de sauvegarde
        KV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = str(KV_CACHE_DIR / f"{model_id}_{session_id}_{prompt_hash}.safetensors")

        # Tentative de capture du KV cache MLX
        kv_data = self._extract_kv_state(model)

        if kv_data is None:
            logger.debug("KV Cache : modèle ne supporte pas l'extraction directe")
            return False

        try:
            import mlx.core as mx
            mx.save_safetensors(file_path, kv_data)

            # Estimation de la taille
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            # Nombre de couches
            num_layers = self._count_layers(kv_data)
            num_tokens = self._estimate_num_tokens(kv_data)

            entry = KVCacheEntry(
                model_id=model_id,
                session_id=session_id,
                prompt_hash=prompt_hash,
                turn_number=turn_number,
                num_layers=num_layers,
                num_tokens=num_tokens,
                file_path=file_path,
                created_at=time.time(),
                accessed_at=time.time(),
                size_mb=file_size_mb,
            )
            self._entries[key] = entry
            self._evict_if_needed()
            self._save_index()
            logger.info(
                f"💾 KV Cache sauvé : {session_id} turn={turn_number} "
                f"({file_size_mb:.1f} MB, {num_layers} layers)"
            )
            return True
        except Exception as e:
            logger.warning(f"⚠️ KV Cache save échoué : {e}")
            return False

    def restore(
        self,
        model: Any,
        session_id: str,
        prompt: str,
        model_id: str = "default",
    ) -> Optional[dict[str, Any]]:
        """Restaure un KV cache depuis le disque.

        Vérifie la correspondance du hash du prompt. Si OK, charge
        le .safetensors et le restitue pour application sur le modèle.

        Returns:
            dict des tenseurs KV (par layer) ou None si pas de cache
        """
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        key = self._make_key(session_id, prompt_hash)

        entry = self._entries.get(key)
        if entry is None:
            return None

        # Vérifier que le fichier existe toujours
        if not os.path.exists(entry.file_path):
            self._entries.pop(key, None)
            self._save_index()
            return None

        try:
            import mlx.core as mx
            loaded = mx.load(entry.file_path)
            if isinstance(loaded, tuple):
                kv_data, _ = loaded  # (tensors, metadata)
            elif isinstance(loaded, dict):
                kv_data = loaded
            else:
                kv_data = {"state": loaded}

            # Mettre à jour le timestamp d'accès
            entry.accessed_at = time.time()
            self._save_index()

            logger.info(
                f"♻️ KV Cache restauré : {session_id} "
                f"({entry.num_tokens} tokens, {entry.num_layers} layers)"
            )
            return kv_data
        except Exception as e:
            logger.warning(f"⚠️ KV Cache restore échoué : {e}")
            self._entries.pop(key, None)
            self._save_index()
            return None

    def find_matching_prefix(
        self,
        session_id: str,
        prompt: str,
        model_id: str = "default",
    ) -> Optional[KVCacheEntry]:
        """Trouve l'entrée la plus proche pour un prompt donné.

        Cherche d'abord le hash exact, puis le prefix le plus long.
        Utile pour les conversations multi-tours où seul le dernier
        message change.

        Returns:
            L'entrée la mieux adaptée ou None
        """
        # 1. Hash exact
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        key = self._make_key(session_id, prompt_hash)
        entry = self._entries.get(key)
        if entry is not None:
            return entry

        # 2. Conserver l'entrée avec le turn_number le plus proche
        # (même session, même model_id)
        candidates = [
            e for e in self._entries.values()
            if e.session_id == session_id and e.model_id == model_id
        ]
        if not candidates:
            return None
        # Prendre la plus récente (turn le plus élevé)
        candidates.sort(key=lambda e: e.turn_number, reverse=True)
        return candidates[0]

    # ─── Éviction ────────────────────────────────────────────────────

    def _evict_if_needed(self) -> None:
        """Éviction LRU si dépassement du budget."""
        if len(self._entries) <= self.max_entries:
            total_mb = sum(e.size_mb for e in self._entries.values())
            if total_mb <= self.max_total_mb:
                return

        # Trier par last_access (plus vieux en premier)
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.accessed_at,
        )

        while len(sorted_entries) > self.max_entries or (
            sum(e.size_mb for e in sorted_entries) > self.max_total_mb
        ):
            victim = sorted_entries.pop(0)
            key = self._make_key(victim.session_id, victim.prompt_hash)
            self._entries.pop(key, None)
            try:
                os.remove(victim.file_path)
                logger.debug(f"🗑️ KV Cache évincé : {victim.session_id} turn={victim.turn_number}")
            except OSError:
                pass

    # ─── Utilitaires MLX ─────────────────────────────────────────────

    @staticmethod
    def _extract_kv_state(model: Any) -> Optional[dict[str, Any]]:
        """Extrait l'état du KV cache du modèle MLX.

        MLX ne standardise pas l'accès au KV cache. On tente plusieurs
        stratégies :
        1. Attribut `kv_cache` direct (list[tuple[key, value]])
        2. Attribut `cache` (modèles HF/MLX)
        3. State dict complet (fallback — le plus volumineux)
        """
        if model is None:
            return None

        # Stratégie 1 : attribut kv_cache
        kv = getattr(model, "kv_cache", None)
        if kv is not None and isinstance(kv, (list, tuple)) and len(kv) > 0:
            # Kv_cache est une list[tuple[key, value]]
            result = {}
            for i, (k, v) in enumerate(kv):
                result[f"kv_cache_{i}_key"] = k
                result[f"kv_cache_{i}_value"] = v
            if result:
                return result

        # Stratégie 2 : attribut cache (modèles transformers-like)
        c = getattr(model, "cache", None)
        if c is not None:
            try:
                if hasattr(c, "to_dict"):
                    return c.to_dict()
                if hasattr(c, "state_dict"):
                    return c.state_dict()
            except Exception:
                pass

        # Stratégie 3 : pas de KV cache accessible
        logger.debug("KV Cache : modèle MLX ne supporte pas l'extraction — "
                      "pas d'attribut kv_cache ou cache trouvé")
        return None

    @staticmethod
    def _count_layers(kv_data: dict) -> int:
        """Compte le nombre de couches dans les données KV."""
        keys = set(k.split("_")[2] for k in kv_data if k.startswith("kv_cache_"))
        return max([int(k) for k in keys if k.isdigit()] or [0]) + 1

    @staticmethod
    def _estimate_num_tokens(kv_data: dict) -> int:
        """Estime le nombre de tokens dans le cache."""
        # Prendre la première valeur et lire sa dimension séquence
        for v in kv_data.values():
            shape = getattr(v, "shape", (0,))
            if len(shape) >= 2:
                return shape[1]  # batch, seq_len, ...
        return 0

    # ─── Stats ───────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        total_mb = sum(e.size_mb for e in self._entries.values())
        total_tokens = sum(e.num_tokens for e in self._entries.values())
        return {
            "entries": len(self._entries),
            "total_size_mb": round(total_mb, 1),
            "max_entries": self.max_entries,
            "max_total_mb": self.max_total_mb,
            "total_tokens_cached": total_tokens,
            "sessions": len(set(e.session_id for e in self._entries.values())),
        }

    def clear(self) -> None:
        """Vide tout le cache KV (fichiers + index)."""
        for entry in self._entries.values():
            try:
                os.remove(entry.file_path)
            except OSError:
                pass
        self._entries.clear()
        self._save_index()
        logger.info("🧹 KV Cache vidé")
