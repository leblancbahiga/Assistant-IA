"""
NURU V8+ — Outil de lecture directe de fichiers (décision Python, pas LLM).

Contrairement au marqueur textuel [LIRE_FICHIER:nom] fragile (rejeté V8),
la décision de lire un fichier est prise côté Python sur métriques objectives :
- Score Gate = FAIBLE/ABSENT
- found_chunks == 0
- grep_documents a trouvé un candidat prometteur

Sécurité :
- Whitelist de répertoires autorisés (pas de lecture arbitraire)
- Rejet des chemins absolus hors whitelist
- Rejet des montées de répertoire (../)
- Limite de taille (5MB max)
- Validation stricte du filename_hint avant ouverture
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Whitelist V8+ : seuls ces répertoires sont accessibles en lecture
ALLOWED_DIRS = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads/Assistant IA/data"),
    os.path.expanduser("~/Downloads/Assistant IA"),
]

# Exclus : Nuru_Brain (boucle d'écho sémantique avec l'index RAG)
EXCLUDED_DIRS = [
    os.path.expanduser("~/Nuru_Brain"),
]

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_READ_CHARS = 5000  # Nombre max de caractères à retourner


def find_and_read_file(filename_hint: str, max_chars: int = MAX_READ_CHARS) -> str:
    """Cherche un fichier par nom (partiel) et retourne son contenu.
    
    Sécurité :
    1. Whitelist : seuls ALLOWED_DIRS sont parcourus
    2. Sanitization : rejet de '../' et chemins absolus
    3. Exclusion : ~/Nuru_Brain ignoré
    4. Limite taille : fichiers > 5MB ignorés (RAM M1 8Go)
    5. Limite caractères : max 5000 chars retournés
    
    Args:
        filename_hint: Nom partiel du fichier à chercher
        max_chars: Nombre max de caractères à retourner
    
    Returns:
        Contenu du fichier ou message d'erreur structuré
    """
    if not filename_hint or not filename_hint.strip():
        return _error("Nom de fichier vide")

    hint = filename_hint.strip()

    # Sanitization V8+ : rejet des tentatives d'évasion
    if ".." in hint or hint.startswith("/") or hint.startswith("~"):
        logger.warning(f"Sanitization : chemin rejeté '{hint}' (../ ou absolu)")
        return _error(f"Chemin non autorisé : {hint}")

    hint_lower = hint.lower()

    # Parcourir les répertoires autorisés
    candidates = []
    for allowed_dir in ALLOWED_DIRS:
        if not os.path.isdir(allowed_dir):
            continue

        for root, dirs, files in os.walk(allowed_dir):
            # Exclure Nuru_Brain
            dirs[:] = [d for d in dirs
                       if os.path.join(root, d) not in EXCLUDED_DIRS]

            for fname in files:
                if hint_lower in fname.lower():
                    filepath = os.path.join(root, fname)
                    candidates.append((filepath, fname))

    if not candidates:
        return _error(f"Fichier '{filename_hint}' introuvable dans les répertoires autorisés")

    # Meilleur candidat : correspondance exacte ou le premier
    exact_matches = [c for c in candidates if hint_lower == c[1].lower()]
    best_path, best_name = exact_matches[0] if exact_matches else candidates[0]

    # Vérification taille
    try:
        fsize = os.path.getsize(best_path)
        if fsize > MAX_FILE_SIZE:
            return _error(f"Fichier trop volumineux : {best_name} ({fsize // 1024}KB > {MAX_FILE_SIZE // 1024}KB)")
    except OSError as e:
        return _error(f"Impossible d'accéder à {best_name}: {e}")

    # Lecture mémoire-safe
    try:
        with open(best_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)

        if len(content) >= max_chars:
            content += "\n...[TRONQUÉ — fichier trop long]"

        return f"=== CONTENU DE {best_name} ===\n{content}\n=== FIN ==="

    except UnicodeDecodeError:
        return _error(f"Format binaire non lisible : {best_name}")
    except Exception as e:
        return _error(f"Erreur lecture {best_name}: {e}")


def _error(message: str) -> str:
    """Retourne un message d'erreur structuré."""
    return f"[ERREUR LECTURE : {message}]"
