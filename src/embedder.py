import asyncio
import mlx.core as mx
import logging
from typing import List, Union
import numpy as np
from src.config import config

logger = logging.getLogger(__name__)

class Embedder:
    """Générateur d'embeddings utilisant MLX (lazy import mlx_embeddings)."""
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.model_id = "mlx-community/multilingual-e5-base-mlx"
        self._model = None
        self._tokenizer = None
        self._initialized = True

    def _load_model(self):
        """Chargement Lazy du modèle d'embedding via mlx_embeddings."""
        if self._model is None:
            try:
                # Import différé pour éviter les dépendances lourdes au démarrage
                import mlx_embeddings
                self._mlx_emb = mlx_embeddings
                # On utilise le chemin résolu (local si possible)
                resolved_path = config.get_model_path(self.model_id)
                self._model, self._tokenizer = mlx_embeddings.load(resolved_path)
                logger.info(f"Embedder MLX chargé depuis : {resolved_path}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de l'embedder : {e}")
                raise

    async def embed(self, text: Union[str, List[str]], is_query: bool = True) -> np.ndarray:
        """Génère des embeddings pour un texte ou une liste de textes.
        
        Args:
            text: Le texte ou la liste de textes à encoder.
            is_query: Si True, ajoute le préfixe 'query: '. Sinon 'passage: '.
        """
        return await asyncio.to_thread(self._embed_sync, text, is_query)

    def _embed_sync(self, text: Union[str, List[str]], is_query: bool = True) -> np.ndarray:
        """Version synchrone pour exécuter dans un thread séparé."""
        import asyncio
        self._load_model()
        
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        prefix = "query: " if is_query else "passage: "
        prefixed_texts = [prefix + t for t in texts]
        
        output = self._mlx_emb.generate(
            self._model, 
            self._tokenizer, 
            prefixed_texts
        )
        
        embeddings = output.text_embeds if output.text_embeds is not None else output.pooler_output
        
        return np.array(embeddings)

    def unload(self):
        """Libère la mémoire Metal."""
        if self._model:
            del self._model
            del self._tokenizer
            self._model = None
            self._tokenizer = None
            mx.metal.clear_cache()
            logger.info("Embedder déchargé de la mémoire Metal.")
