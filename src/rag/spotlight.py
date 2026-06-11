"""
NURU V10 — Spotlight Search : recherche + lecture directe sur macOS.

Utilise l'index Spotlight pour chercher, puis LIT le contenu des fichiers trouvés.
C'est la clé : pas juste les noms de fichiers, mais le CONTENU réel.
"""
import subprocess
import logging
import os
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions lisibles
READABLE_EXTS = {".txt", ".md", ".py", ".csv", ".json", ".html", ".rtf", ".docx", ".pdf", ".pptx", ".xlsx"}


@dataclass
class SpotlightResult:
    path: str
    filename: str
    content: str = ""  # Contenu réel du fichier (extrait)
    relevance: float = 0.0


class SpotlightSearch:
    """Recherche via Spotlight (mdfind) + lecture du contenu."""

    def __init__(self):
        self._is_macos = os.uname().sysname == "Darwin"
        self._search_history: list = []
        if not self._is_macos:
            logger.warning("Spotlight non disponible (pas macOS)")

    def search(self, query: str, scope: Optional[str] = None, max_results: int = 10,
               read_content: bool = True) -> List[SpotlightResult]:
        """
        Cherche via Spotlight et lit le contenu des fichiers trouvés.

        Args:
            query: Terme de recherche
            scope: Répertoire limité (ex: ~/Desktop) ou None pour tout
            max_results: Nombre max de résultats
            read_content: Si True, lit le contenu des fichiers
        """
        if not self._is_macos:
            return []

        # Construire la commande mdfind
        cmd = ["mdfind"]
        if scope:
            scope_path = Path(scope).expanduser()
            if scope_path.exists():
                cmd.extend(["-onlyin", str(scope_path)])
        cmd.append(query)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return []

            paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            results = []

            for path in paths[:max_results]:
                p = Path(path)
                if not p.exists() or not p.is_file():
                    continue
                if p.suffix.lower() not in READABLE_EXTS:
                    continue

                content = ""
                if read_content:
                    content = self._read_file(p, max_chars=2000)

                results.append(SpotlightResult(
                    path=str(p),
                    filename=p.name,
                    content=content,
                    relevance=1.0,
                ))

            self._search_history.append({"query": query, "results": len(results)})
            return results

        except subprocess.TimeoutExpired:
            logger.warning(f"Spotlight timeout: {query}")
            return []
        except Exception as e:
            logger.error(f"Erreur Spotlight: {e}")
            return []

    def _read_file(self, path: Path, max_chars: int = 2000) -> str:
        """Lit le contenu d'un fichier selon son type."""
        suffix = path.suffix.lower()
        try:
            if suffix in {".txt", ".md", ".py", ".csv", ".json", ".html"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                return text[:max_chars]
            elif suffix == ".pdf":
                import pymupdf
                doc = pymupdf.open(str(path))
                text = ""
                for page in doc:
                    text += page.get_text()
                    if len(text) > max_chars:
                        break
                doc.close()
                return text[:max_chars]
            elif suffix == ".docx":
                from docx import Document
                doc = Document(str(path))
                text = "\n".join([p.text for p in doc.paragraphs])
                return text[:max_chars]
            elif suffix == ".pptx":
                from pptx import Presentation
                prs = Presentation(str(path))
                text = ""
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text += shape.text + "\n"
                    if len(text) > max_chars:
                        break
                return text[:max_chars]
            elif suffix == ".xlsx":
                from openpyxl import load_workbook
                wb = load_workbook(str(path), data_only=True)
                text = ""
                for sheet in wb.sheetnames:
                    ws = wb[sheet]
                    for row in ws.iter_rows(values_only=True):
                        text += " ".join([str(c) for c in row if c is not None]) + "\n"
                    if len(text) > max_chars:
                        break
                return text[:max_chars]
            return ""
        except Exception as e:
            logger.debug(f"Erreur lecture {path.name}: {e}")
            return ""

    def get_history(self) -> list:
        return list(self._search_history)
