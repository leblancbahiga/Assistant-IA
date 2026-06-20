"""Tests for logging configuration."""

import logging
import tempfile
from pathlib import Path

import pytest

from src.logging_config import JSONFormatter, NURULogger, get_logger


class TestNURULogger:
    """Test NURU logger configuration."""

    def test_singleton_instance(self):
        """Test that NURULogger is a singleton."""
        logger1 = NURULogger()
        logger2 = NURULogger()
        assert logger1 is logger2

    def test_get_logger_json_format(self):
        """Test logger creation with JSON format."""
        nuru = NURULogger(log_format="json")
        logger = nuru.get_logger("test_json")
        assert logger is not None
        assert logger.level == logging.INFO

    def test_get_logger_text_format(self):
        """Test logger creation with text format."""
        nuru = NURULogger(log_format="text")
        logger = nuru.get_logger("test_text")
        assert logger is not None

    def test_logger_with_file(self):
        """Test logger writing to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            nuru = NURULogger(log_file=str(log_file))
            logger = nuru.get_logger("test_file")
            logger.info("Test message")
            assert log_file.exists()

    def test_convenience_function(self):
        """Test get_logger convenience function."""
        logger = get_logger("test_convenience")
        assert isinstance(logger, logging.Logger)

    def test_json_formatter(self):
        """Test JSON formatter output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        assert "timestamp" in formatted
        assert "level" in formatted
        assert "Test message" in formatted
