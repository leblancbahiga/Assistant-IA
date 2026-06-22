"""NURU Vision Pipeline — Phase 2.

Vision écran + documents :
  - Capture d'écran macOS via screencapture
  - OCR via tesserocr (fallback pytesseract)
  - Analyse cloud : image envoyée au LLM cloud
"""

from .screen import ScreenCapture, ScreenResult
from .doc_vision import DocumentVision, DocVisionResult

__all__ = [
    "ScreenCapture", "ScreenResult",
    "DocumentVision", "DocVisionResult",
]
