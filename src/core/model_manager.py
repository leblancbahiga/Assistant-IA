"""ModelManager — Contrôle strict de la RAM unifiée Apple Silicon.

Garantit qu'un seul modèle ML est chargé à la fois dans les ~4.5 Go
de RAM disponible sur M1 8 Go. Décharge explicitement après usage
avec gc.collect() + mx.clear_cache().

Usage:
    mm = ModelManager()
    async with mm.use_llm() as llm:
        response = llm.generate(prompt)
    # LLM automatiquement déchargé après keep_alive ou à la demande
"""
import gc
import logging
import asyncio
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ModelManager:
    """Cycle de vie des modèles ML : un seul chargé à la fois.

    Politique mémoire :
    - Un SEUL modèle chargé simultanément (embedder | reranker | llm)
    - Déchargement explicite via unload()
    - Keep-alive configurable (défaut 5 min) avant auto-déchargement
    - Vérification RAM avant chargement
    """

    MODEL_TYPES = {"embedder", "reranker", "llm"}

    def __init__(self, keep_alive_seconds: int = 300):
        self._active_model: Any = None
        self._active_tokenizer: Any = None
        self._active_type: Optional[str] = None
        self._active_model_id: Optional[str] = None
        self._keep_alive = keep_alive_seconds
        self._unload_task: Optional[asyncio.Task] = None

    # ─── Propriétés ───

    @property
    def is_loaded(self) -> bool:
        return self._active_model is not None

    @property
    def active_type(self) -> Optional[str]:
        return self._active_type

    @property
    def active_model_id(self) -> Optional[str]:
        return self._active_model_id

    # ─── Chargement / Déchargement ───

    def load(self, model_type: str, loader: Callable, model_id: str = "") -> Any:
        """Charge un modèle. Décharge le précédent si type différent.

        Args:
            model_type: 'embedder' | 'reranker' | 'llm'
            loader: Fonction de chargement (peut être synchrone ou async)
            model_id: Identifiant du modèle (pour logs)

        Returns:
            Le modèle chargé
        """
        if model_type not in self.MODEL_TYPES:
            raise ValueError(f"Type de modèle invalide: {model_type}")

        # Décharger si type différent
        if self._active_type is not None and self._active_type != model_type:
            self.unload()

        # Charger si pas déjà en cache
        if self._active_model is None:
            logger.info(f"📦 Chargement {model_type}: {model_id or 'default'}")
            result = loader()
            if isinstance(result, tuple):
                self._active_model, self._active_tokenizer = result[0], result[1] if len(result) > 1 else None
            else:
                self._active_model = result
            self._active_type = model_type
            self._active_model_id = model_id
            logger.info(f"✅ {model_type} chargé")

        self._cancel_unload()
        return self._active_model

    def unload(self):
        """Décharge le modèle actif et vide les caches."""
        if self._active_model is not None:
            logger.info(f"🧹 Déchargement {self._active_type or 'modèle'}...")
            del self._active_model
            if self._active_tokenizer is not None:
                del self._active_tokenizer
            self._active_model = None
            self._active_tokenizer = None
            self._active_type = None
            self._active_model_id = None
            gc.collect()

            # Nettoyage cache Metal (MLX)
            try:
                import mlx.core as mx
                mx.clear_cache()
            except Exception:
                pass

            logger.info("✅ Modèle déchargé, cache vidé")

    # ─── Keep-Alive ───

    def _schedule_unload(self):
        """Planifie le déchargement après keep_alive secondes d'inactivité."""
        self._cancel_unload()

        async def _delayed():
            try:
                await asyncio.sleep(self._keep_alive)
                if self._active_model is not None:
                    logger.info(f"⏰ Keep-alive expiré ({self._keep_alive}s). Déchargement auto.")
                    self.unload()
            except asyncio.CancelledError:
                pass

        try:
            self._unload_task = asyncio.create_task(_delayed())
        except RuntimeError:
            pass

    def _cancel_unload(self):
        if self._unload_task is not None:
            self._unload_task.cancel()
            self._unload_task = None

    def keep_alive(self):
        """Réinitialise le timer de keep-alive (appelé après chaque usage)."""
        self._schedule_unload()

    # ─── RAM Guard ───

    @staticmethod
    def get_free_ram_gb() -> float:
        """Retourne la RAM disponible en Go."""
        import psutil
        return psutil.virtual_memory().available / (1024**3)

    @staticmethod
    def is_ram_safe(min_free_gb: float = 0.5) -> bool:
        """Vérifie si la RAM est suffisante pour charger un modèle."""
        free = ModelManager.get_free_ram_gb()
        if free < min_free_gb:
            logger.warning(f"⚠️ RAM critique: {free:.2f} Go libre (min: {min_free_gb})")
            return False
        return True

    # ─── Context Managers ───

    @asynccontextmanager
    async def use_llm(self, loader: Callable, model_id: str = ""):
        """Contexte pour utilisation du LLM : charge, yield, décharge après keep-alive."""
        try:
            yield self.load("llm", loader, model_id)
        finally:
            self.keep_alive()

    @asynccontextmanager
    async def use_embedder(self, loader: Callable, model_id: str = ""):
        """Contexte pour utilisation de l'embedder."""
        try:
            yield self.load("embedder", loader, model_id)
        finally:
            self.keep_alive()

    @asynccontextmanager
    async def use_reranker(self, loader: Callable, model_id: str = ""):
        """Contexte pour utilisation du reranker (déchargement immédiat après)."""
        try:
            yield self.load("reranker", loader, model_id)
        finally:
            self.unload()  # Reranker : toujours décharger immédiatement
