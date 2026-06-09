"""
NURU V8+ — Orchestrateur de recherche multi-stratégie.

Lance plusieurs stratégies de recherche en parallèle (vectoriel, FTS, grep, HyDE)
et fusionne les résultats via RRF normalisé.

Fondation V8+ (Sprint 0) :
- Vérification RAM avant lancement (ne pas swapper sur M1 8Go)
- Early stopping si score vectoriel > 0.75

Implémentation complète dans Sprint 4.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Seuil RAM : ne pas lancer la recherche lourde (grep, HyDE) si < 2 Go libre
MIN_RAM_FOR_HEAVY_SEARCH_MB = 2000  # 2 Go


def check_ram_available() -> tuple[bool, int]:
    """Vérifie si la RAM disponible est suffisante pour les recherches lourdes.
    
    Returns:
        (ok, free_mb): True si RAM >= seuil, False sinon. free_mb = RAM dispo.
    """
    try:
        import psutil
        free_mb = psutil.virtual_memory().available / (1024 * 1024)
        ok = free_mb >= MIN_RAM_FOR_HEAVY_SEARCH_MB
        if not ok:
            logger.info(
                f"RAM insuffisante pour recherche lourde : {free_mb:.0f} MB "
                f"(seuil: {MIN_RAM_FOR_HEAVY_SEARCH_MB} MB)"
            )
        return ok, int(free_mb)
    except Exception:
        return True, 9999  # Si psutil échoue, on autorise
