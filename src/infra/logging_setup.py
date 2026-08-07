"""Configuration des logs structurés avec loguru pour NURU V8+.

Intercepte les logs standard `logging` et les reformate avec loguru.
S'installe en appelant `setup_logging()` au démarrage de l'application.
"""
import sys
import logging
from pathlib import Path
from loguru import logger


class InterceptHandler(logging.Handler):
    """Intercepte les logs standard `logging` et les redirige vers loguru."""

    def emit(self, record: logging.LogRecord):
        # V17 FIX : filtrer le bruit pypdf avant même la vérification de niveau
        if record.name.startswith("pypdf") and record.levelno < logging.ERROR:
            return
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            if frame.f_back:
                frame = frame.f_back
                depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(
    log_file: str | Path = "logs/nuru.log",
    rotation: str = "10 MB",
    retention: str = "30 days",
    level: str = "INFO",
):
    """Configure loguru avec fichier tournant et affichage console colorisé.

    Args:
        log_file: Chemin du fichier de log (relatif à CWD ou absolu)
        rotation: Taille max avant rotation (ex: "10 MB", "1 day")
        retention: Durée de conservation (ex: "30 days")
        level: Niveau de log minimum pour la console ("DEBUG", "INFO", "WARNING")
    """
    # V16 FIX : taire les warnings pypdf (PDFs corrompus, centaines de lignes)
    for logger_name in ("pypdf", "pypdf._reader"):
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    # Supprime les handlers loguru par défaut
    logger.remove()

    # Console : colorisée, niveaux INFO+ par défaut
    logger.add(
        sys.stderr,
        format=(
            "<level>{level.icon}</level> "
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <6}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=False,
    )

    # Fichier : rotation, retention, JSON-like structuré
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON structuré (Phase 2 : correlation ID + logs JSON)
    json_path = log_path.with_suffix(".jsonl")
    logger.add(
        str(json_path),
        format="{time} | {level} | {name} | {function}:{line} | {message}",
        serialize=True,
        rotation=rotation,
        retention=retention,
        level="DEBUG",
        backtrace=True,
        diagnose=False,
    )

    # Fichier texte avec rotation
    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss,SSS} | {level: <6} | {name}:{line} | {message}{exception}",
        rotation=rotation,
        retention=retention,
        level="DEBUG",
        backtrace=True,
        diagnose=False,
    )

    # V16 AUDIT FIX QW11 : logs interceptés à INFO (était DEBUG) — I/O CPU -30%
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

    logger.info(f"📋 Logs configurés — fichier: {log_path} | rotation: {rotation} | retention: {retention}")


def get_logger(name: str):
    """Retourne un logger loguru pour un module donné.

    Usage::
        from src.infra.logging_setup import get_logger
        logger = get_logger(__name__)
    """
    return logger.bind(name=name)
