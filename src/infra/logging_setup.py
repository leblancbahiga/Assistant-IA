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
    level: str = "DEBUG",
):
    """Configure loguru avec fichier tournant et affichage console colorisé.

    Args:
        log_file: Chemin du fichier de log (relatif à CWD ou absolu)
        rotation: Taille max avant rotation (ex: "10 MB", "1 day")
        retention: Durée de conservation (ex: "30 days")
        level: Niveau de log minimum pour la console ("DEBUG", "INFO", "WARNING")
    """
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
    logger.add(
        str(log_path),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <6} | {name}:{function}:{line} | {message}"
        ),
        level="DEBUG",
        rotation=rotation,
        retention=retention,
        compression="gz",
        backtrace=True,
        diagnose=False,
    )

    # Interception des logs `logging` standard → loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.DEBUG, force=True)

    logger.info(f"📋 Logs configurés — fichier: {log_path} | rotation: {rotation} | retention: {retention}")


def get_logger(name: str):
    """Retourne un logger loguru pour un module donné.

    Usage::
        from src.infra.logging_setup import get_logger
        logger = get_logger(__name__)
    """
    return logger.bind(name=name)
