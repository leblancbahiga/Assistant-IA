"""Vision écran — capture, OCR, analyse cloud.

Capture de l'écran macOS via screencapture, OCR local,
et analyse contextuelle via LLM cloud.
Consentement requis avant toute capture (V15 P2 #25).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.privacy.consent_layer import SensorType

logger = logging.getLogger(__name__)


@dataclass
class ScreenConfig:
    """Configuration de capture écran."""
    format: str = "png"
    resolution_scale: float = 0.5
    max_file_size_mb: int = 5
    include_cursor: bool = False
    enable_ocr: bool = True
    ocr_language: str = "fra+eng"


@dataclass
class ScreenResult:
    """Résultat d'analyse d'écran."""
    screenshot_path: Optional[Path] = None
    ocr_text: str = ""
    width: int = 0
    height: int = 0
    analysis: str = ""
    error: Optional[str] = None


class ScreenCapture:
    """Capture et analyse d'écran macOS.

    Usage :
        screen = ScreenCapture()
        result = await screen.capture()
        print(result.ocr_text)
        # Avec analyse LLM :
        result = await screen.capture_and_analyze(llm_client)
        print(result.analysis)
    """

    def __init__(self, config: Optional[ScreenConfig] = None, consent_layer=None):
        self.config = config or ScreenConfig()
        self._consent = consent_layer

    @property
    def consent(self):
        """Accès paresseux au ConsentLayer."""
        if self._consent is None:
            from src.privacy import get_consent_layer
            self._consent = get_consent_layer()
        return self._consent

    async def capture(
        self, region: Optional[tuple[int, int, int, int]] = None
    ) -> ScreenResult:
        """Capture l'écran (ou une région).

        Vérifie le consentement screen_capture avant activation.

        Args:
            region: (x, y, w, h) optionnel pour capture partielle

        Returns:
            ScreenResult avec le chemin du screenshot et l'OCR
        """
        # V15 P2 #25 : vérification consentement capture écran
        if not self.consent.request_access(
            SensorType.SCREEN_CAPTURE,
            purpose="Capture écran pour analyse",
            session_only=True,
        ):
            logger.warning("Screen: accès refusé par consentement")
            return ScreenResult(error="Capture écran refusée par consentement")

        tmp = Path(tempfile.mktemp(suffix=f".{self.config.format}"))
        try:
            cmd = ["screencapture", "-x"]
            if region:
                cmd.extend(["-R", f"{region[0]},{region[1]},{region[2]},{region[3]}"])
            if not self.config.include_cursor:
                cmd.append("-C")
            cmd.append(str(tmp))

            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, timeout=10
            )
            if proc.returncode != 0:
                return ScreenResult(error=f"screencapture: {proc.stderr.decode()}")

            width, height = self._get_dimensions(tmp)
            if width == 0:
                return ScreenResult(error="Impossible de lire les dimensions")

            ocr_text = ""
            if self.config.enable_ocr:
                ocr_text = await self._ocr(tmp)

            return ScreenResult(
                screenshot_path=tmp,
                ocr_text=ocr_text,
                width=width,
                height=height,
            )

        except subprocess.TimeoutExpired:
            return ScreenResult(error="Capture timeout")
        except Exception as e:
            return ScreenResult(error=f"Erreur capture: {e}")

    async def capture_and_analyze(self, llm_client: Optional[object] = None) -> ScreenResult:
        """Capture + analyse LLM.

        Vérifie aussi le consentement avant capture.
        """
        result = await self.capture()
        if result.error or not result.screenshot_path:
            return result
        if llm_client is None:
            return result
        try:
            with open(result.screenshot_path, "rb") as f:
                img_b64 = __import__("base64").b64encode(f.read()).decode()
            analysis = await llm_client.analyze_image(img_b64)
            result.analysis = analysis
        except Exception as e:
            result.analysis = f"Erreur analyse: {e}"
        return result

    def _get_dimensions(self, path: Path) -> tuple[int, int]:
        """Lit les dimensions de l'image via PIL."""
        try:
            from PIL import Image
            with Image.open(path) as img:
                return img.size
        except ImportError:
            return (0, 0)
        except Exception:
            return (0, 0)

    async def _ocr(self, path: Path) -> str:
        """OCR local via macOS Vision framework."""
        try:
            import subprocess
            script = f"""
            use framework "Vision"
            use scripting additions

            set imgPath to "{path}"
            set req to current application's VNRecognizeTextRequest's alloc's init()
            set handler to current application's VNImageRequestHandler's alloc's initWithURL:(current application's |NSURL|'s fileURLWithPath:imgPath) options:{{}}
            handler's performRequests:{{req}} |error|:(missing value)
            set results to req's results()
            set text to ""
            repeat with r in results
                set text to text & (r's topCandidates:(1)'s firstObject()'s string()) & linefeed
            end repeat
            return text
            """
            proc = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30,
            )
            return proc.stdout.strip()
        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return ""
