"""V17 FIX : utilitaire partagé d'embedding synchrone.

Factorise _embed_sync dupliqué dans episodic.py, procedural.py,
semantic.py et errors.py. Chaque classe garde une méthode privée
qui délègue ici, évitant l'import croisé.
"""

import numpy as np
from src.embedder import Embedder


def embed_sync(text: str, embedder: Embedder | None = None) -> np.ndarray:
    """Calcule un embedding de manière synchrone.

    Args:
        text: Texte à vectoriser.
        embedder: Instance partagée de l'embedder (créée si None).

    Returns:
        Vecteur d'embedding numpy.
    """
    if embedder is None:
        embedder = Embedder()
    return embedder.embed_sync(text, is_query=False)
