"""
Reranker 2 étages pour NURU V4.

Étape 1 - Retrieval : multilingual-e5-base → top 15 (via RAGEngine)
Étape 2 - Reranking : cross-encoder/ms-marco-MiniLM-L-6-v2 → top 3
Étape 3 - LLM : Contexte réduit aux 3 meilleurs chunks

Modèle : 22 Mo seulement, compatible MPS/M1, zéro dépendances complexes.
"""
import logging
import gc
import numpy as np
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

class CrossEncoderReranker:
    """
    Reranker cross-encoder 2 étages.
    Léger (22 Mo) et compatible MPS pour M1 8 Go.
    """
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k_retrieval: int = 15,
        top_k_rerank: int = 3,
        min_score_for_relevance: float = 0.0,
    ):
        self.model_name = model_name
        self.top_k_retrieval = top_k_retrieval
        self.top_k_rerank = top_k_rerank
        self.min_score_for_relevance = min_score_for_relevance
        self._model = None
        self._loaded = False
        self.embedder = None
    
    def set_embedder(self, embedder):
        """Stocke l'embedder pour l'étape 1 (injection de dépendances)."""
        self.embedder = embedder
    
    def load_model(self):
        """Charge le cross-encoder MiniLM (lazy loading)."""
        if self._loaded and self._model is not None:
            return
        
        try:
            from sentence_transformers import CrossEncoder
            import torch
            
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            logger.info(f"🧮 Chargement cross-encoder: {self.model_name} sur {device}")
            self._model = CrossEncoder(self.model_name, device=device)
            self._loaded = True
            logger.info("✅ Cross-encoder MiniLM chargé")
        except Exception as e:
            logger.error(f"❌ Erreur chargement cross-encoder: {e}")
            self._model = None
    
    def unload(self):
        """Décharge le cross-encoder (appelé par RAMMonitor)."""
        if self._model is not None:
            logger.info("🧹 Déchargement du cross-encoder...")
            del self._model
            self._model = None
            self._loaded = False
            gc.collect()
            
            # Nettoyage du cache MPS/Metal
            try:
                import mlx.core as mx
                mx.metal.clear_cache()
            except Exception:
                pass
            try:
                import torch
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except Exception:
                pass
            
            logger.info("✅ Cross-encoder déchargé")
    
    async def rerank(
        self,
        query: str,
        results: List[Tuple[str, str, float]],
        top_k: Optional[int] = None,
    ) -> List[Tuple[str, str, float]]:
        """
        Re-ranking via cross-encoder.
        
        Args:
            query: Requête utilisateur
            results: Chunks candidats (content, source, original_score)
            top_k: Nombre final de résultats (défaut: top_k_rerank)
        
        Returns:
            Top_k chunks rerankés
        """
        if not results:
            return []
        
        if top_k is None:
            top_k = self.top_k_rerank
        
        if self._model is None:
            logger.warning("⚠️ Cross-encoder non disponible, tri original")
            sorted_results = sorted(results, key=lambda x: x[2], reverse=True)
            return sorted_results[:top_k]
        
        try:
            # Préparer les paires (query, chunk)
            pairs = [(query, chunk_content) for chunk_content, _, _ in results]
            
            # Inférence cross-encoder
            scores = self._model.predict(pairs, show_progress_bar=False)
            
            # Correction 3 : Normalisation robuste via np.atleast_1d (évite crash sur scalaire)
            scores = np.atleast_1d(scores)
            scores_norm = 1.0 / (1.0 + np.exp(-scores))
            
            # Construire les résultats rerankés
            import re
            query_words = set(re.findall(r'\w+', query.lower()))
            
            reranked = []
            for i, (content, source, _) in enumerate(results):
                score = float(scores_norm[i]) if i < len(scores_norm) else 0.0
                
                # Bonus source (mot-clé dans le nom de fichier)
                source_words = set(re.findall(r'\w+', source.lower()))
                if query_words & source_words:
                    score = min(score + 0.08, 1.0)
                
                if score >= self.min_score_for_relevance:
                    reranked.append((content, source, round(score, 3)))
            
            # Trier et limiter
            reranked.sort(key=lambda x: x[2], reverse=True)
            final = reranked[:top_k]
            
            logger.info(
                f"📊 Cross-encoder: {len(results)} → {len(final)} gardés "
                f"| Top1: {final[0][2] if final else 0:.3f}"
            )
            
            return final
            
        except Exception as e:
            logger.error(f"❌ Erreur cross-encoder: {e}")
            sorted_results = sorted(results, key=lambda x: x[2], reverse=True)
            return sorted_results[:top_k]
