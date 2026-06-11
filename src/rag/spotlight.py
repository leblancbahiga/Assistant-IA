"""
NURU V10 — Spotlight Search : recherche + lecture directe sur macOS.

Utilise l'index Spotlight pour chercher, puis LIT le contenu des fichiers trouvés.
"""
import subprocess
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions lisibles
READABLE_EXTS = {".txt", ".md", ".py", ".csv", ".json", ".html", ".rtf", ".docx", ".pdf", ".pptx", ".xlsx"}

# Mots vides à extraire des requêtes
STOP_WORDS = {
    'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'ou',
    'est', 'sont', 'a', 'ai', 'as', 'avons', 'avez', 'ont',
    'parle', 'moi', 'dit', 'raconte', 'montre', 'donne',
    'quel', 'quelle', 'quels', 'quelles', 'que', 'qui',
    'comment', 'pourquoi', 'quand', 'où', 'combien',
    'the', 'a', 'an', 'and', 'or', 'is', 'are', 'was', 'were',
}

# Dossiers du projet à exclure
PROJECT_DIRS = {
    '/Downloads/Assistant IA/src/',
    '/Downloads/Assistant IA/tests/',
    '/Downloads/Assistant IA/scripts/',
    '/Downloads/Assistant IA/.venv/',
    '/Downloads/Assistant IA/docs/',
}


@dataclass
class SpotlightResult:
    path: str
    filename: str
    content: str = ""
    relevance: float = 0.0


class SpotlightSearch:
    """Recherche via Spotlight (mdfind) + lecture du contenu."""

    def __init__(self):
        self._is_macos = os.uname().sysname == "Darwin"
        self._search_history: list = []
        if not self._is_macos:
            logger.warning("Spotlight non disponible (pas macOS)")

    def _extract_key_terms(self, query: str) -> List[str]:
        """Extrait les termes clés d'une requête (supprime les mots vides)."""
        words = re.findall(r'\w{2,}', query.lower())
        return [w for w in words if w not in STOP_WORDS]

    def search(self, query: str, scope: Optional[str] = None, max_results: int = 10,
               read_content: bool = True) -> List[SpotlightResult]:
        """Cherche via Spotlight et lit le contenu des fichiers."""
        if not self._is_macos:
            return []

        # Extraire les termes clés
        key_terms = self._extract_key_terms(query)
        if not key_terms:
            return []

        # Construire la commande mdfind
        search_query = " ".join(key_terms[:3])
        cmd = ["mdfind"]
        if scope:
            scope_path = Path(scope).expanduser()
            if scope_path.exists():
                cmd.extend(["-onlyin", str(scope_path)])
        cmd.append(search_query)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return []

            paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            results = []

            for path in paths[:max_results * 3]:
                p = Path(path)
                if not p.exists() or not p.is_file():
                    continue
                if p.suffix.lower() not in READABLE_EXTS:
                    continue

                # Exclure les fichiers du projet
                path_str = str(p)
                if any(d in path_str for d in PROJECT_DIRS):
                    continue
                if p.suffix.lower() == '.py' and 'Assistant IA' in path_str:
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

                if len(results) >= max_results:
                    break

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
