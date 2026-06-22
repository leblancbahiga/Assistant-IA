"""Vision documents — analyse d'images, OCR, extraction structurée.

Analyse de documents (PDF, images) :
  - OCR multi-langue
  - Extraction de structure (titres, paragraphes, tableaux)
  - Analyse cloud via LLM (vision)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DocVisionConfig:
    """Configuration de vision document."""
    ocr_language: str = "fra+eng"
    max_pages: int = 10
    extract_tables: bool = True
    extract_structure: bool = True
    llm_analysis: bool = True
    max_image_size_mb: int = 5


@dataclass
class DocSection:
    """Section d'un document extrait."""
    title: str = ""
    content: str = ""
    level: int = 0
    page: int = 0


@dataclass
class DocVisionResult:
    """Résultat d'analyse de document."""
    text: str = ""
    sections: list[DocSection] = field(default_factory=list)
    ocr_confidence: float = 0.0
    pages: int = 0
    analysis: str = ""        # Résumé LLM
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text_length": len(self.text),
            "n_sections": len(self.sections),
            "ocr_confidence": self.ocr_confidence,
            "pages": self.pages,
            "has_analysis": bool(self.analysis),
        }


class DocumentVision:
    """Analyse de documents par vision.

    Usage :
        doc_viz = DocumentVision()
        result = await doc_viz.analyze("~/document.pdf")
        result = await doc_viz.analyze_image("~/photo.jpg")
    """

    def __init__(self, config: Optional[DocVisionConfig] = None):
        self.config = config or DocVisionConfig()

    async def analyze(self, path: str | Path, llm_client=None) -> DocVisionResult:
        """Analyse un document (image ou PDF).

        Args:
            path: Chemin vers le fichier
            llm_client: Client LLM optionnel pour l'analyse

        Returns:
            DocVisionResult
        """
        path = Path(path).expanduser()
        if not path.exists():
            return DocVisionResult(error=f"Fichier introuvable: {path}")

        ext = path.suffix.lower()

        try:
            if ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
                return await self.analyze_image(path, llm_client)
            elif ext == ".pdf":
                return await self.analyze_pdf(path, llm_client)
            else:
                return DocVisionResult(error=f"Format non supporté: {ext}")
        except Exception as e:
            logger.error(f"Erreur analyse document: {e}")
            return DocVisionResult(error=str(e))

    async def analyze_image(self, path: Path, llm_client=None) -> DocVisionResult:
        """Analyse une image unique."""
        ocr_text = await self._ocr_image(path)

        sections = []
        if self.config.extract_structure:
            sections = self._extract_sections(ocr_text)

        result = DocVisionResult(
            text=ocr_text,
            sections=sections,
            ocr_confidence=0.5,  # Estimation
            pages=1,
        )

        if llm_client and self.config.llm_analysis:
            result.analysis = await self._llm_analyze(path, llm_client)

        return result

    async def analyze_pdf(self, path: Path, llm_client=None) -> DocVisionResult:
        """Analyse un PDF page par page."""
        try:
            import pymupdf  # PyMuPDF
            doc = pymupdf.open(str(path))
        except ImportError:
            logger.warning("pymupdf non installé")
            return DocVisionResult(text="", pages=0, error="pymupdf requis pour PDF")

        all_text = []
        sections = []
        max_p = min(len(doc), self.config.max_pages)

        for i in range(max_p):
            page = doc[i]
            text_raw = page.get_text()
            text = str(text_raw) if text_raw else ""
            if text:
                text = text.strip()
                if text:
                    all_text.append(text)
                if self.config.extract_structure:
                    sections.extend(self._extract_sections(text, page=i+1))

        result = DocVisionResult(
            text="\n\n".join(all_text),
            sections=sections,
            pages=max_p,
        )

        doc.close()
        return result

    async def _ocr_image(self, path: Path) -> str:
        """OCR sur une image."""
        try:
            import tesserocr  # type: ignore
            from PIL import Image
            img = Image.open(path)
            return tesserocr.image_to_text(img, lang=self.config.ocr_language).strip()
        except ImportError:
            try:
                import pytesseract  # type: ignore
                from PIL import Image
                img = Image.open(path)
                return pytesseract.image_to_string(img, lang=self.config.ocr_language).strip()
            except ImportError:
                logger.warning("Aucun OCR installé")
                return f"[OCR non disponible — image: {path.name}]"

    def _extract_sections(self, text: str, page: int = 0) -> list[DocSection]:
        """Extraction basique de structure."""
        sections = []
        lines = text.split("\n")
        current_section = DocSection(page=page)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Détection de titre (ligne courte, majuscules ou numérique)
            if len(line) < 80 and (line.isupper() or line[0].isdigit()):
                if current_section.content:
                    sections.append(current_section)
                current_section = DocSection(title=line, level=1, page=page)
            else:
                if current_section.content:
                    current_section.content += "\n" + line
                else:
                    current_section.content = line

        if current_section.content:
            sections.append(current_section)
        return sections

    async def _llm_analyze(self, image_path: Path, llm_client) -> str:
        """Analyse via LLM vision."""
        try:
            import base64
            image_data = image_path.read_bytes()
            if len(image_data) > self.config.max_image_size_mb * 1024 * 1024:
                return "[Image trop volumineuse pour l'analyse LLM]"

            encoded = base64.b64encode(image_data).decode("utf-8")
            ext = image_path.suffix.lstrip(".") or "png"

            response = await llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyse ce document/image. "
                         "Extrais : titres, dates, montants, personnes, actions demandées. "
                         "Résumé en 5 lignes max."},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{ext};base64,{encoded}"}
                        },
                    ],
                }],
                max_tokens=500,
                temperature=0.2,
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Erreur analyse LLM: {e}")
            return ""
