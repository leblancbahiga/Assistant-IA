"""
NURU V16 -- Self-Consistency Engine (Wang et al. 2023).

Genere 3 reponses independantes -> vote majoritaire par similarite cosinus.
Reduit les hallucinations de ~40% (d'apres papier original).
Compatible M1 8Go : generation sequentielle, pas parallele.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyResult:
    """Resultat d'une generation Self-Consistency."""
    responses: list[str]                          # Les 3 reponses brutes
    final_response: str                           # Reponse consensuelle
    votes: dict[str, int]                         # cluster -> count
    similarity_matrix: list[list[float]]          # Matrice similarite pour debug
    consensus_score: float                        # 0-1, 1 = accord total
    clusters_detail: list[list[str]] = field(default_factory=list)  # Details clusters


class SelfConsistencyEngine:
    """
    Moteur Self-Consistency 3-way voting.
    
    Usage:
        engine = SelfConsistencyEngine(n_samples=3, temperature=0.7)
        result = await engine.generate_consistent(
            query="Qu'est-ce que la photosynthese ?",
            context="Les plantes vertes...",
            generate_fn=llm.generate,
            system_prompt="Tu es NURU...",
        )
        # result.final_response = reponse validee par consensus
    """
    
    def __init__(
        self,
        n_samples: int = 3,
        temperature: float = 0.7,
        similarity_threshold: float = 0.25,
        min_cluster_size: int = 1,
    ):
        """
        Args:
            n_samples: Nombre de reponses a generer (defaut 3)
            temperature: Temperature pour diversite (0.5-0.9)
            similarity_threshold: Seuil Jaccard/TF-IDF pour cluster (0.7-0.9)
            min_cluster_size: Taille min cluster pour etre considere
        """
        if n_samples < 2:
            raise ValueError("n_samples doit être >= 2")
        self.n_samples = n_samples
        self.temperature = temperature
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size
    
    async def generate_consistent(
        self,
        query: str,
        context: str,
        generate_fn: Callable[[str, float], Awaitable[str]],
        system_prompt: str = "",
    ) -> ConsistencyResult:
        """
        Genere N reponses et vote par similarite semantique.
        
        Args:
            query: Question utilisateur
            context: Contexte RAG/memoire
            generate_fn: fn(prompt, temperature) -> response
            system_prompt: Prompt systeme
            
        Returns:
            ConsistencyResult avec reponse consensuelle
        """
        # 1. Construire le prompt complet
        prompt = self._build_prompt(query, context, system_prompt)
        
        # 2. Generer N reponses (sequentielle pour economiser RAM M1)
        responses = []
        for i in range(self.n_samples):
            logger.debug(f"SelfConsistency: echantillon {i+1}/{self.n_samples}")
            try:
                resp = await generate_fn(prompt, self.temperature)
                responses.append(resp.strip())
            except Exception as e:
                logger.warning(f"Echec echantillon {i+1}: {e}")
                responses.append("")
        
        # 3. Clustering par similarite (TF-IDF simple, pas d'embedding couteux)
        clusters = self._cluster_responses(responses)
        
        # 4. Vote majoritaire = cluster le plus grand
        best_cluster = max(clusters, key=len)
        final_response = self._select_representative(best_cluster)
        
        # 5. Score de consensus
        consensus = len(best_cluster) / max(len(responses), 1)
        
        return ConsistencyResult(
            responses=responses,
            final_response=final_response,
            votes={f"cluster_{i}": len(c) for i, c in enumerate(clusters)},
            similarity_matrix=self._similarity_matrix(responses),
            consensus_score=consensus,
            clusters_detail=clusters,
        )
    
    def _build_prompt(self, query: str, context: str, system_prompt: str) -> str:
        """Construit le prompt complet."""
        parts = []
        if system_prompt:
            parts.append(f"<|system|>\n{system_prompt}\n<|end|>")
        if context:
            parts.append(f"## CONTEXTE\n{context}\n")
        parts.append(f"<|user|>\n{query}\n<|end|>\n<|assistant|>\n")
        return "\n".join(parts)
    
    def _cluster_responses(self, responses: list[str]) -> list[list[str]]:
        """Clustering simple par similarite Jaccard (mots-cles)."""
        if not responses:
            return []
        
        # Filtrer reponses vides
        valid = [(i, r) for i, r in enumerate(responses) if r.strip()]
        if len(valid) < 2:
            return [[r] for _, r in valid]
        
        texts = [r for _, r in valid]
        
        # Vectorisation TF-IDF legere
        from sklearn.feature_extraction.text import TfidfVectorizer
        
        vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
        tfidf = vectorizer.fit_transform(texts)
        
        # Similarite cosinus
        sim_matrix = (tfidf * tfidf.T).toarray()
        
        # Clustering glouton simple
        clusters = []
        assigned = set()
        
        for i in range(len(texts)):
            if i in assigned:
                continue
            cluster = [texts[i]]
            assigned.add(i)
            for j in range(i + 1, len(texts)):
                if j not in assigned and sim_matrix[i, j] >= self.similarity_threshold:
                    cluster.append(texts[j])
                    assigned.add(j)
            clusters.append(cluster)
        
        return clusters
    
    def _select_representative(self, cluster: list[str]) -> str:
        """Selectionne la reponse la plus 'centrale' du cluster."""
        if len(cluster) == 1:
            return cluster[0]
        # Celle qui a la plus grande similarite moyenne aux autres
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
        tfidf = vectorizer.fit_transform(cluster)
        sim = (tfidf * tfidf.T).toarray()
        avg_sim = sim.mean(axis=1)
        return cluster[int(np.argmax(avg_sim))]
    
    def _similarity_matrix(self, responses: list[str]) -> list[list[float]]:
        """Matrice de similarite pour debug/dashboard."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        valid = [r for r in responses if r.strip()]
        if len(valid) < 2:
            return [[1.0]]
        vectorizer = TfidfVectorizer(stop_words='english', max_features=100)
        tfidf = vectorizer.fit_transform(valid)
        return (tfidf * tfidf.T).toarray().tolist()


# Fonction helper pour integration facile
async def run_self_consistency(
    query: str,
    context: str,
    local_llm,  # Instance LocalLLM
    system_prompt: str = "",
    n_samples: int = 3,
    temperature: float = 0.7,
) -> ConsistencyResult:
    """Wrapper simple pour utilisation directe."""
    engine = SelfConsistencyEngine(n_samples=n_samples, temperature=temperature)
    
    async def gen_fn(prompt: str, temp: float) -> str:
        return await local_llm.generate(prompt, intent="RAG", temperature=temp)
    
    return await engine.generate_consistent(
        query=query,
        context=context,
        generate_fn=gen_fn,
        system_prompt=system_prompt,
    )