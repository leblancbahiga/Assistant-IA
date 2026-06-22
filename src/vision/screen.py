"""Vision écran — capture, OCR, analyse cloud.

Capture de l'écran macOS via screencapture, OCR local,
et analyse contextuelle via LLM cloud.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScreenConfig:
    """Configuration de capture écran."""
    format: str = "png"
    resolution_scale: float = 0.5     # 50% = ~2 Mo au lieu de 8 Mo
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
    analysis: str = ""               # Analyse LLM du contenu
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

    def __init__(self, config: Optional[ScreenConfig] = None):
        self.config = config or ScreenConfig()

    async def capture(self, region: Optional[tuple[int, int, int, int]] = None) -> ScreenResult:
        """Capture l'écran (ou une région).

        Args:
            region: (x, y, w, h) optionnel pour capture partielle

        Returns:
            ScreenResult avec le chemin du screenshot et l'OCR
        """
        tmp = Path(tempfile.mktemp(suffix=f".{self.config.format}"))
        try:
            # Capture via screencapture macOS
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

            # Dimensions
            width, height = self._get_dimensions(tmp)
            if width == 0:
                return ScreenResult(error="Impossible de lire les dimensions")

            # OCR
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
            logger.error(f"Erreur capture: {e}")
            return ScreenResult(error=str(e))

    async def capture_and_analyze(self, llm_client) -> ScreenResult:
        """Capture + analyse LLM du contenu."""
        base = await self.capture()
        if base.error or not base.screenshot_path:
            return base

        try:
            # Envoyer l'image au LLM pour analyse
            import base64 as b64
            image_data = base.screenshot_path.read_bytes()
            encoded = b64.b64encode(image_data).decode("utf-8")

            # Prompt d'analyse
            response = await llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Décris ce qui est visible sur l'écran. "
                         "Sois précis : quelles applications, fenêtres, contenu, "
                         "boutons sont affichés ?"},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{self.config.format};base64,{encoded}"}
                        },
                    ],
                }],
                max_tokens=500,
                temperature=0.3,
            )
            base.analysis = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Erreur analyse LLM: {e}")
            base.analysis = "[Analyse LLM indisponible]"

        return base

    async def _ocr(self, image_path: Path) -> str:
        """OCR via tesserocr (fallback pytesseract)."""
        try:
            # Essayer tesserocr (C++, plus rapide)
            import tesserocr  # type: ignore
            from PIL import Image

            img = Image.open(image_path)
            text = tesserocr.image_to_text(img, lang=self.config.ocr_language)
            return text.strip()
        except ImportError:
            try:
                # Fallback pytesseract
                import pytesseract  # type: ignore
                from PIL import Image

                img = Image.open(image_path)
                text = pytesseract.image_to_string(img, lang=self.config.ocr_language)
                return text.strip()
            except ImportError:
                logger.warning("Aucun OCR installé (tesserocr ou pytesseract)")
                return ""
        except Exception as e:
            logger.error(f"Erreur OCR: {e}")
            return ""

    def _get_dimensions(self, image_path: Path) -> tuple[int, int]:
        """Récupère les dimensions de l'image."""
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size
        except ImportError:
            return (0, 0)
        except Exception:
            return (0, 0)


# Import asyncio pour la compatibilité async
import asyncio
