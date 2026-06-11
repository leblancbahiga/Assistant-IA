"""
NURU V10 — Spotlight Search : recherche directe sur macOS via mdfind.

Utilise l'index Spotlight du système pour chercher dans TOUS les fichiers
de l'ordinateur. Pas besoin de notre propre index — Spotlight indexe tout.

Usage:
    spotlight = SpotlightSearch()
    results = spotlight.search("BEACCOM")
    results = spotlight.search("rapport filière riz", scope="~/Desktop")
"""
import subprocess
import logging
import os
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class SpotlightResult:
    path: str
    filename: str
    content_snippet: str = ""
    relevance: float = 0.0

class SpotlightSearch:
    """Recherche via Spotlight (mdfind) sur macOS."""
    
    def __init__(self):
        self._is_macos = os.uname().sysname == "Darwin"
        self._search_history: list = []
        if not self._is_macos:
            logger.warning("Spotlight non disponible (pas macOS)")
    
    def search(self, query: str, scope: Optional[str] = None, max_results: int = 20) -> List[SpotlightResult]:
        """
        Cherche via Spotlight.
        
        Args:
            query: Terme de recherche
            scope: Répertoire limité (ex: ~/Desktop) ou None pour tout
            max_results: Nombre max de résultats
        """
        if not self._is_macos:
            return []
        
        # Construire la commande mdfind
        cmd = ["mdfind"]
        
        # Limitation par répertoire
        if scope:
            scope_path = Path(scope).expanduser()
            if scope_path.exists():
                cmd.extend(["-onlyin", str(scope_path)])
        
        # Ajouter la requête
        cmd.append(query)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.warning(f"mdfind erreur: {result.stderr}")
                return []
            
            # Parser les résultats
            paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            
            results = []
            for path in paths[:max_results]:
                p = Path(path)
                if p.exists() and p.is_file():
                    results.append(SpotlightResult(
                        path=str(p),
                        filename=p.name,
                        relevance=1.0,
                    ))
            
            self._search_history.append({"query": query, "results": len(results)})
            return results
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Spotlight timeout pour: {query}")
            return []
        except Exception as e:
            logger.error(f"Erreur Spotlight: {e}")
            return []
    
    def search_content(self, query: str, max_results: int = 10) -> List[dict]:
        """Cherche dans le CONTENU des fichiers (plus lent mais plus complet)."""
        results = self.search(query, max_results=max_results)
        
        enriched = []
        for r in results:
            try:
                p = Path(r.path)
                if p.suffix.lower() in {".txt", ".md", ".py", ".csv", ".json"}:
                    content = p.read_text(encoding="utf-8", errors="ignore")[:500]
                    enriched.append({
                        "path": r.path,
                        "filename": r.filename,
                        "content": content,
                    })
                elif p.suffix.lower() == ".pdf":
                    enriched.append({
                        "path": r.path,
                        "filename": r.filename,
                        "content": "[PDF — ouvrir pour voir le contenu]",
                    })
                else:
                    enriched.append({
                        "path": r.path,
                        "filename": r.filename,
                        "content": "",
                    })
            except Exception:
                enriched.append({
                    "path": r.path,
                    "filename": r.filename,
                    "content": "",
                })
        
        return enriched
    
    def get_history(self) -> list:
        return list(self._search_history)
