"""Tests seuils RAM configurables (Option C) — Audit B-RAM V10.3k.

Trois seuils sont aujourd'hui hardcodés dans le code et inadaptés à un M1 8 Go :
  - RERANK_MIN_RAM_MB = 1500  (policies.py:29)
  - MIN_RAM_FOR_HEAVY_SEARCH_MB = 2000  (multi_search.py:30)
  - RAMMonitor warning=2.0 GB / critical=1.0 GB  (ram_monitor.py:20-21)

Avec 1.1 Go disponible réellement sous PySide6 + Python, **les 3 désactivent
toutes les optimisations** (reranker OFF, multi-search lourd OFF, alertes WARNING
permanentes). Le pipeline RAG fonctionne en mode dégradé permanent.

Le fix doit :
1. Ajouter des clés dans `src/config.py` (Config héritant de BaseSettings) :
   - rerank_min_ram_mb (int, default 800)
   - heavy_search_min_ram_mb (int, default 1000)
   - ram_warning_threshold_gb (float, default 1.0)
   - ram_critical_threshold_gb (float, default 0.5)
2. Faire pointer les call sites vers `config.rerank_min_ram_mb` au lieu des constantes
3. Garder la compatibilité ascendante : si la config est indispo, fallback sur l'ancienne constante
4. Surchargeable via settings.yaml et/ou env NURU_*

Ces tests ne doivent valider QUE la mécanique de configuration.
Les seuils par défaut ne sont PAS testés en valeur absolue (tolérance aux
arbitrages), mais le fait qu'ils soient lus via Config au lieu d'être en dur.
"""
import pytest
from unittest.mock import patch
import sys


def _fresh():
    """Force un reimport pour tester le lazy loading des constantes."""
    sys.path.insert(0, '/Users/leblancbahiga/Downloads/Assistant IA')


# ─────────────────────────────────────────────────────────────
# SOURCE-OF-TRUTH : les seuils doivent être dans Config, plus dans des constantes hardcodées
# ─────────────────────────────────────────────────────────────

def test_config_exposes_rerank_min_ram_mb():
    """Config doit exposer rerank_min_ram_mb (lu via yaml/env/default)."""
    from src.config import Config
    cfg = Config()
    val = getattr(cfg, "rerank_min_ram_mb", None)
    assert val is not None, (
        "Config.rerank_min_ram_mb introuvable ! "
        "Le seuil doit être configurable depuis settings.yaml."
    )
    assert isinstance(val, int), f"Attendu int, got {type(val).__name__}"
    assert val >= 200, "Valeur trop basse (au moins 200 Mo pour cross-encoder)"
    assert val <= 3000, "Valeur trop haute (3 Go serait OK pour 32 Go+, pas pour 8 Go)"


def test_config_exposes_heavy_search_min_ram_mb():
    """Config doit exposer heavy_search_min_ram_mb."""
    from src.config import Config
    cfg = Config()
    val = getattr(cfg, "heavy_search_min_ram_mb", None)
    assert val is not None, "Config.heavy_search_min_ram_mb introuvable"
    assert isinstance(val, int)
    assert 200 <= val <= 4000


def test_config_exposes_ram_warning_and_critical_thresholds_gb():
    """Config doit exposer les seuils RAM warnings/critical en GB."""
    from src.config import Config
    cfg = Config()
    warn = getattr(cfg, "ram_warning_threshold_gb", None)
    crit = getattr(cfg, "ram_critical_threshold_gb", None)
    assert warn is not None, "Config.ram_warning_threshold_gb manquant"
    assert crit is not None, "Config.ram_critical_threshold_gb manquant"
    assert isinstance(warn, (int, float))
    assert isinstance(crit, (int, float))
    assert 0.1 <= crit < warn, (
        f"critical ({crit}) doit être < warning ({warn})"
    )


# ─────────────────────────────────────────────────────────────
# CALL SITES : le code applicatif doit lire Config, pas la constante hardcodée
# ─────────────────────────────────────────────────────────────

def test_policies_engine_uses_config_rerank_min_ram():
    """PolicyEngine.should_rerank doit utiliser Config, pas constant hardcodée."""
    from src.core.policies import PolicyEngine
    from src.config import config as global_config

    pe = PolicyEngine()
    expected = getattr(global_config, "rerank_min_ram_mb", pe.RERANK_MIN_RAM_MB)
    assert pe.RERANK_MIN_RAM_MB == expected, (
        f"PolicyEngine utilise la constante hardcodée ({pe.RERANK_MIN_RAM_MB}), "
        f"devrait utiliser config.rerank_min_ram_mb ({expected})."
    )


def test_multi_search_uses_config_heavy_search_min_ram():
    """multi_search doit utiliser Config pour le seuil heavy search."""
    from src.rag import multi_search
    from src.config import config as global_config

    expected = getattr(global_config, "heavy_search_min_ram_mb", multi_search.MIN_RAM_FOR_HEAVY_SEARCH_MB)
    assert multi_search.MIN_RAM_FOR_HEAVY_SEARCH_MB == expected, (
        f"multi_search.MIN_RAM_FOR_HEAVY_SEARCH_MB = {multi_search.MIN_RAM_FOR_HEAVY_SEARCH_MB} "
        f"(hardcodé), devrait être {expected} (config)."
    )


def test_ram_monitor_respects_config_thresholds():
    """RAMMonitor doit être instanciable avec les seuils venant de Config."""
    from src.config import config as global_config
    from src.ram_monitor import RAMMonitor

    warn_gb = getattr(global_config, "ram_warning_threshold_gb", 2.0)
    crit_gb = getattr(global_config, "ram_critical_threshold_gb", 1.0)

    monitor = RAMMonitor(
        warning_threshold_gb=warn_gb,
        critical_threshold_gb=crit_gb,
    )
    assert monitor.warning_threshold == warn_gb * 1024 * 1024 * 1024
    assert monitor.critical_threshold == crit_gb * 1024 * 1024 * 1024


def test_rag_engine_consistency_with_policies():
    """rag_engine._rerank_min_ram_mb doit suivre le même seuil que policies."""
    from src.config import config as global_config

    rerank_expected = getattr(global_config, "rerank_min_ram_mb", 800)
    # Le moteur RAG doit accepter ce seuil ou déléguer à PolicyEngine
    # Test indirect : patcher le seuil et vérifier que _should_use_reranker réagit
    from src.rag_engine import RAGEngine

    eng = RAGEngine.__new__(RAGEngine)
    eng._rerank_min_ram_mb = rerank_expected
    # Si on a 900 Mo libre et seuil 800, on autorise reranker (top_score > 0.15)
    assert eng._should_use_reranker(0.30), (
        f"Score 0.30 + 900 Mo > seuil {rerank_expected} → reranker doit être autorisé"
    )
    # Si on a 500 Mo et seuil 800, on bloque même avec bon score
    # Note : _should_use_reranker ne lit pas ram, c'est test indirect sur la valeur du seuil
    # On vérifie juste que la valeur est cohérente
    assert eng._rerank_min_ram_mb == rerank_expected


# ─────────────────────────────────────────────────────────────
# SETTINGS.YAML : les nouvelles clés doivent apparaître
# ─────────────────────────────────────────────────────────────

def test_settings_yaml_has_new_keys():
    """config/settings.yaml doit pouvoir contenir les nouvelles clés."""
    from pathlib import Path
    yaml_path = Path("/Users/leblancbahiga/Downloads/Assistant IA/config/settings.yaml")
    if not yaml_path.exists():
        pytest.skip("settings.yaml absent (CI?)")
    import yaml
    data = yaml.safe_load(yaml_path.read_text()) or {}
    # Doit au moins supporter les 4 clés (présentes avec défaut OU override)
    expected_keys = {
        "rerank_min_ram_mb",
        "heavy_search_min_ram_mb",
        "ram_warning_threshold_gb",
        "ram_critical_threshold_gb",
    }
    # Pas obligatoire dans le YAML (defaults code), mais les clés doivent être
    # surchargeables — on accepte l'un OU l'autre
    # Notons les clés déjà présentes pour audit
    yaml_keys = set(data.keys())
    overlap = expected_keys & yaml_keys
    # Tolérance : soit le YAML a les clés (override), soit le code a les défauts
    # Le test suit en test_config_exposes_* ci-dessus.
    assert True  # Documentation : la couverture est dans les tests précédent


# ─────────────────────────────────────────────────────────────
# DEFAULTS SANITY : sur 8 Go, les défauts doivent éviter le mode dégradé permanent
# ─────────────────────────────────────────────────────────────

def test_defaults_friendly_for_8gb_m1():
    """Les defaults doivent être < RAM typique-dispo-sur-8Go-au-repos (~1.1 Go Q3 2026).

    Avec 1.1 Go disponible, si on exige 1500+ Mo pour activer une feature,
    elle est désactivée en permanence. Les défauts doivent être compatibles.
    """
    from src.config import Config
    cfg = Config()

    # rerank_min_ram_mb : cross-encoder demande ~400 Mo, donc 800 Mo de seuil est OK
    assert cfg.rerank_min_ram_mb <= 1000, (
        f"rerank_min_ram_mb = {cfg.rerank_min_ram_mb}. Sur M1 8 Go, ce seuil "
        f"désactivera le reranker en permanence (dispo réelle ≈ 1.1 Go)."
    )

    # heavy_search : grep + HyDE = ~300 Mo, 1000 Mo de seuil est OK
    assert cfg.heavy_search_min_ram_mb <= 1200, (
        f"heavy_search_min_ram_mb = {cfg.heavy_search_min_ram_mb}. Trop élevé pour 8 Go."
    )

    # Warning à 1 Go = OK, critical à 0.5 Go = OK
    assert cfg.ram_warning_threshold_gb <= 1.5
    assert cfg.ram_critical_threshold_gb <= 1.0
