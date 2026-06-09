"""
NURU V8+ — Recherche directe dans les fichiers texte (fallback grep).

Fallback quand le RAG vectoriel échoue : cherche par mots-clés directement
dans les fichiers des répertoires monitorés.

Exclusions :
- ~/Nuru_Brain/ (évite les boucles d'écho sémantique avec les exports)
- Fichiers > 2MB (limite mémoire M1 8Go)
- Extensions binaires non supportées

Utilisation :
    from src.rag.file_search import grep_documents
    results = grep_documents("rendement riz Palabek", max_results=3)
"""
import os
import re
import time
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

# Répertoires de documents monitorés
DOC_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads/Assistant IA/data"),
]

# Exclusion V8+ : Nuru_Brain — les exports markdown de l'index RAG
# ne doivent pas être rescannés (boucle d'écho sémantique)
EXCLUDE_DIRS = [
    os.path.expanduser("~/Nuru_Brain"),
    os.path.expanduser("~/Nuru_Brain/sources"),
]

SUPPORTED_EXTS = {".txt", ".md", ".py", ".json", ".yaml", ".yml",
                  ".csv", ".xml", ".html", ".pdf"}  # V8+ : PDF supporté via pypdf
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB — sécurité mémoire M1 8Go
MAX_RESULTS_DEFAULT = 5

# V8+ : Cache TTL pour les résultats grep (60s)
# Évite de rescanner le disque pour la même requête en peu de temps
_grep_cache: dict[str, tuple[float, list[dict]]] = {}
GREP_CACHE_TTL = 60  # secondes


def _get_cached(query: str) -> list[dict] | None:
    """Retourne les résultats en cache si encore valides."""
    key = query.lower().strip()
    entry = _grep_cache.get(key)
    if entry and (time.time() - entry[0]) < GREP_CACHE_TTL:
        return entry[1]
    return None


def _set_cache(query: str, results: list[dict]):
    """Stocke les résultats dans le cache."""
    key = query.lower().strip()
    _grep_cache[key] = (time.time(), results)
    # Nettoyer les entrées expirées (max 100)
    if len(_grep_cache) > 100:
        now = time.time()
        expired = [k for k, v in _grep_cache.items() if (now - v[0]) > GREP_CACHE_TTL]
        for k in expired:
            del _grep_cache[k]


def grep_documents(
    query: str,
    max_results: int = MAX_RESULTS_DEFAULT,
) -> list[dict]:
    """Cherche le query dans les fichiers des répertoires monitorés.
    
    Lecture ligne par ligne via read() avec limite de taille pour éviter
    de charger des fichiers entiers en mémoire sur M1 8Go.
    
    V8+ : Cache TTL 60s — ne rescanner le disque que si nécessaire.
    
    Args:
        query: Texte à chercher (mots-clés)
        max_results: Nombre max de résultats (défaut: 5)
    
    Returns:
        Liste de {path, filename, line, content, preview, score}
    """
    if not query or not query.strip():
        return []

    # V8+ : Vérifier le cache TTL
    cached = _get_cached(query)
    if cached is not None:
        logger.debug(f"🔍 grep_documents cache HIT pour '{query[:30]}'")
        return cached[:max_results]
    logger.debug(f"🔍 grep_documents cache MISS pour '{query[:30]}' — scan disque")

    query_lower = query.lower().strip()
    words = [w for w in re.findall(r'\w+', query_lower) if len(w) > 2]

    if not words:
        return []

    results = []
    seen_paths = set()

    for doc_dir in DOC_DIRS:
        if not os.path.isdir(doc_dir):
            continue

        for root, dirs, files in os.walk(doc_dir):
            # V8+ : Exclure Nuru_Brain et sous-répertoires
            dirs[:] = [d for d in dirs
                       if os.path.join(root, d) not in EXCLUDE_DIRS
                       and not _is_nuru_brain_path(os.path.join(root, d))]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTS:
                    continue

                filepath = os.path.join(root, fname)

                # Vérification exclusion (sécurité doublon)
                if _is_nuru_brain_path(filepath):
                    continue

                if filepath in seen_paths:
                    continue

                try:
                    fsize = os.path.getsize(filepath)
                except OSError:
                    continue

                if fsize > MAX_FILE_SIZE or fsize == 0:
                    continue

                score = _score_file(filepath, fname, words)
                if score > 0.3:
                    preview = _read_preview(filepath)
                    if preview:
                        seen_paths.add(filepath)
                        results.append({
                            "path": filepath,
                            "filename": fname,
                            "content": preview[:2000],
                            "preview": preview[:200].replace("\n", " "),
                            "score": round(score, 3),
                        })

                if len(results) >= max_results * 2:  # collecter plus pour tri
                    break

            if len(results) >= max_results * 2:
                break

        if len(results) >= max_results * 2:
            break

    # Trier par score décroissant
    results.sort(key=lambda x: x["score"], reverse=True)
    # V8+ : Mettre en cache pour 60s
    _set_cache(query, results)
    return results[:max_results]


# ── Fonctions internes ──


def _is_nuru_brain_path(filepath: str) -> bool:
    """Vérifie si un chemin appartient à ~/Nuru_Brain."""
    nb_path = os.path.expanduser("~/Nuru_Brain")
    try:
        return os.path.commonpath([nb_path, filepath]) == nb_path
    except ValueError:
        return False


def _extract_pdf_text(filepath: str, max_chars: int = 5000) -> str:
    """Extraction de texte d'un PDF via pypdf (mémoire-safe, limité).
    
    Retourne jusqu'à max_chars caractères. En cas d'échec, retourne ''.
    Le fallback silencieux permet de ne pas casser le pipeline grep.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(filepath)
        text = []
        total = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text.append(page_text)
            total += len(page_text)
            if total >= max_chars:
                break
        return "\n".join(text)[:max_chars]
    except Exception as e:
        logger.debug(f"Extraction PDF échouée pour {os.path.basename(filepath)}: {e}")
        return ""


def _score_file(filepath: str, fname: str, words: list[str]) -> float:
    """Score de pertinence : match nom fichier + contenu."""
    score = 0.0

    # 1. Score sur le nom de fichier
    fname_lower = fname.lower()
    name_matches = sum(1 for w in words if w in fname_lower)
    if name_matches > 0:
        score += 0.4 * (name_matches / len(words))

    # 2. Score sur le contenu
    content = ""
    ext = os.path.splitext(fname)[1].lower()
    try:
        if ext == ".pdf":
            content = _extract_pdf_text(filepath, max_chars=4096)
        else:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4096)
    except Exception:
        pass

    if content:
        content_lower = content.lower()
        content_matches = sum(1 for w in words if w in content_lower)
        if content_matches > 0:
            score += 0.6 * (content_matches / len(words))

    return min(1.0, score)


def _read_preview(filepath: str, max_chars: int = 2000) -> str:
    """Lit un extrait du fichier pour le retour (mémoire-safe)."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".pdf":
            return _extract_pdf_text(filepath, max_chars=max_chars)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    except Exception:
        return ""
