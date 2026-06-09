"""
NURU V8+ — Audit d'index RAG.

Compare les fichiers présents dans les répertoires data/ avec les entrées
dans l'index sqlite-vec. Produit un rapport des documents manquants,
partiellement indexés, ou orphelins.

Utile pour savoir si l'index est fiable avant d'implémenter des
stratégies de fallback.

Usage :
    from src.rag.index_health import check_index_health
    report = check_index_health()
    print(report.summary())
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Optional
from src.config import config

logger = logging.getLogger(__name__)

# Répertoires de documents surveillés
DOC_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads/Assistant IA/data"),
]

# Extensions de fichiers indexables
INDEXED_EXTS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".py"}


@dataclass
class IndexHealthReport:
    """Rapport complet de l'état de l'index RAG."""
    total_in_index: int = 0
    files_on_disk: int = 0
    matched: int = 0
    missing_from_index: list[str] = field(default_factory=list)
    orphaned_in_index: list[str] = field(default_factory=list)
    last_checked: str = ""

    def summary(self) -> str:
        """Résumé concis."""
        pct = 0
        if self.files_on_disk > 0:
            pct = int(self.matched / self.files_on_disk * 100)
        status = "✅ Sain" if pct >= 90 else "⚠️ Dégradé" if pct >= 50 else "❌ Critique"
        return (
            f"[IndexHealth] {status} — "
            f"{self.total_in_index} dans l'index, "
            f"{self.files_on_disk} sur disque, "
            f"{pct}% correspondance. "
            f"{len(self.missing_from_index)} fichiers non indexés, "
            f"{len(self.orphaned_in_index)} entrées orphelines."
        )

    def to_dict(self) -> dict:
        return {
            "status": "healthy" if self.matched >= self.files_on_disk * 0.9 else "degraded",
            "total_in_index": self.total_in_index,
            "files_on_disk": self.files_on_disk,
            "matched": self.matched,
            "match_pct": round(self.matched / max(self.files_on_disk, 1) * 100, 1),
            "missing_count": len(self.missing_from_index),
            "orphaned_count": len(self.orphaned_in_index),
            "missing_samples": self.missing_from_index[:5],
            "orphaned_samples": self.orphaned_in_index[:5],
        }


def check_index_health() -> IndexHealthReport:
    """Compare disque vs index et produit un rapport.

    Returns:
        IndexHealthReport avec matched, missing, orphaned counts.
    """
    report = IndexHealthReport()

    from datetime import datetime
    report.last_checked = datetime.now().isoformat()

    # 1. Compter les entrées dans l'index sqlite-vec
    try:
        from src.rag_engine import RAGEngine
        engine = RAGEngine()
        conn = engine._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        report.total_in_index = count

        # Récupérer la liste des sources indexées
        indexed_sources = set()
        rows = conn.execute(
            "SELECT DISTINCT source FROM chunks"
        ).fetchall()
        indexed_sources = {r[0] for r in rows}
        conn.close()
    except Exception as e:
        logger.warning(f"Impossible d'accéder à l'index : {e}")
        return report

    # 2. Lister les fichiers sur disque dans les répertoires monitorés
    disk_files = set()
    for doc_dir in DOC_DIRS:
        if not os.path.isdir(doc_dir):
            continue
        # Exclure Nuru_Brain
        nb_path = os.path.expanduser("~/Nuru_Brain")
        for root, dirs, files in os.walk(doc_dir):
            # Skip Nuru_Brain
            if os.path.commonpath([nb_path, root]) == nb_path:
                dirs[:] = []
                continue
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in INDEXED_EXTS:
                    disk_files.add(fname)

    report.files_on_disk = len(disk_files)

    # 3. Comparer : les fichiers sur disque sont-ils dans l'index ?
    for fname in sorted(disk_files):
        # L'index stocke les sources sous forme de nom de fichier
        if fname in indexed_sources:
            report.matched += 1
        else:
            report.missing_from_index.append(fname)

    # 4. Entrées orphelines : dans l'index mais plus sur disque
    for source in indexed_sources:
        # Extraire le nom du fichier du path de source
        source_fname = os.path.basename(source)
        if source_fname not in disk_files:
            report.orphaned_in_index.append(source)

    # Limiter les listes (ne pas flooder les logs)
    report.missing_from_index = report.missing_from_index[:20]
    report.orphaned_in_index = report.orphaned_in_index[:20]

    logger.info(report.summary())
    return report
