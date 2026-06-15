"""Test d'intégration B-RAM — montre que les nouveaux seuils permettent
d'activer le reranker et la multi-search là où les anciens les désactivaient.

Avant (seuils hardcodés) : 1098 Mo dispo < 1500 Mo → reranker OFF permanent
                         1098 Mo dispo < 2000 Mo → multi-search OFF permanent

Après (Option C défauts) : 1098 Mo dispo > 800 Mo → reranker autorisé
                          1098 Mo dispo > 1000 Mo → multi-search autorisé

Note : on ne lance pas vraiment de modèle MLX (coûteux). On vérifie la
logique de seuil seule.
"""
import pytest


def test_old_seuils_would_have_disabled_everything():
    """Démonstration : avec les anciens seuils, même 1.1 Go ne suffit pas."""
    old_rerank_min = 1500
    old_heavy_min = 2000
    available_mb = 1100  # RAM typique M1 8 Go après Qt6 + Python

    rerank_old_ok = available_mb >= old_rerank_min
    heavy_old_ok = available_mb >= old_heavy_min

    assert not rerank_old_ok, "AVANT: 1.1 Go < 1500 → reranker OFF (validé)"
    assert not heavy_old_ok, "AVANT: 1.1 Go < 2000 → multi-search OFF (validé)"


def test_new_seuils_enable_optimizations_on_8gb():
    """Après le fix Option C, 1.1 Go doit suffire pour activer le reranker."""
    from src.config import config

    new_rerank_min = getattr(config, "rerank_min_ram_mb", 800)
    new_heavy_min = getattr(config, "heavy_search_min_ram_mb", 1000)
    available_mb = 1100  # RAM typique M1 8 Go après Qt6 + Python

    rerank_new_ok = available_mb >= new_rerank_min
    heavy_new_ok = available_mb >= new_heavy_min

    assert rerank_new_ok, (
        f"APRÈS: devrait activer reranker. 1.1 Go vs seuil {new_rerank_min} Mo."
    )
    assert heavy_new_ok, (
        f"APRÈS: devrait activer multi-search. 1.1 Go vs seuil {new_heavy_min} Mo."
    )


def test_rerank_threshold_realistic_minimum():
    """Cross-encoder ms-marco-MiniLM-L-6-v2 demande ~250 Mo chargé."""
    from src.config import config
    val = config.rerank_min_ram_mb
    # Le cross-encoder charge en plus du modèle MLX de base. Min réaliste : 600 Mo.
    assert val >= 400, (
        f"rerank_min_ram_mb = {val} trop bas pour cross-encoder "
        f"(min réaliste ~400 Mo avec marge)."
    )
    # Max réaliste pour ne pas être inutile sur 8 Go
    assert val <= 1500, (
        f"rerank_min_ram_mb = {val} trop haut, désactive systématiquement "
        f"sur 8 Go (dispo réelle ≈ 1.1 Go). Réduisez à <1200."
    )


def test_heavy_search_threshold_realistic_minimum():
    """HyDE (Cloud) + grep parallèle = ~200 Mo supplémentaires."""
    from src.config import config
    val = config.heavy_search_min_ram_mb
    assert 400 <= val <= 1500, (
        f"heavy_search_min_ram_mb = {val} hors plage réaliste [400..1500]."
    )
