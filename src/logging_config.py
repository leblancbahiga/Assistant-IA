"""Centralized logging configuration for NURU V12."""

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Optional
import sys


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


class NURULogger:
    """NURU logging configuration manager."""

    _instance: Optional["NURULogger"] = None
    _loggers: dict = {}

    def __new__(cls, *args: object, **kwargs: object) -> "NURULogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        log_level: str = "INFO",
        log_format: str = "json",
        log_file: Optional[str] = None,
        audit_file: Optional[str] = None,
    ):
        """Initialize NURU logger.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_format: Format type ('json' or 'text')
            log_file: Path to main log file
            audit_file: Path to audit log file
        """
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_format = log_format
        self.log_file = log_file
        self.audit_file = audit_file

    def get_logger(self, name: str, is_audit: bool = False) -> logging.Logger:
        """Get or create a logger.

        Args:
            name: Logger name (typically __name__)
            is_audit: Whether this is an audit logger

        Returns:
            Configured logger instance
        """
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)

        if self.log_format == "json":
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler
        log_path = self.audit_file if is_audit else self.log_file
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=50 * 1024 * 1024, backupCount=5
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        self._loggers[name] = logger
        return logger

    @classmethod
    def initialize(
        cls,
        log_level: str = "INFO",
        log_format: str = "json",
        log_file: Optional[str] = None,
        audit_file: Optional[str] = None,
    ) -> "NURULogger":
        """Initialize the singleton logger.

        Args:
            log_level: Logging level
            log_format: Format type
            log_file: Main log file path
            audit_file: Audit log file path

        Returns:
            NURULogger singleton instance
        """
        instance = cls(log_level, log_format, log_file, audit_file)
        return instance


# Convenience function
def get_logger(name: str, is_audit: bool = False) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name
        is_audit: Whether this is an audit logger

    Returns:
        Logger instance
    """
    nuru_logger = NURULogger()
    return nuru_logger.get_logger(name, is_audit)
