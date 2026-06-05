"""NURU V4.5 — Initialisation des logs avec loguru (V4.5 Phase 0)."""
import logging
from pathlib import Path


def setup_logging(log_file: Path):
    """Configure les logs structurés avec loguru (remplace logging.basicConfig V3).

    Redirige tous les logs standard `logging` vers loguru avec :
    - Console colorisée
    - Rotation fichier (10 MB, 30 jours de retention)
    - Compression gzip des archives
    """
    from src.infra.logging_setup import setup_logging as _setup_loguru

    _setup_loguru(
        log_file=log_file,
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
    )
