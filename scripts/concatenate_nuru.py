#!/usr/bin/env python3
"""NURU — Concaténation complète du code source pour audit par experts externes.

Génère NURU_CODE_EXPERTS_2026-08-06.txt :
- TOUS les fichiers source (src/, config/, racine) — pas de sélection biaisée
- Table des matières numérotée
- En-tête par fichier (chemin, lignes, statut git)
- Section finale : git diff des modifications non commitées + git log récent
- Exclut : .venv, .git, __pycache__, data/, logs/, binaires, caches HF

Usage : unset PYTHONPATH && .venv/bin/python scripts/concatenate_nuru.py
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/leblancbahiga/Downloads/Assistant IA")
OUT = ROOT / "NURU_CODE_EXPERTS_2026-08-06.txt"

# Extensions incluses (code + config textuelle)
INCLUDE_EXT = {".py", ".yaml", ".yml", ".toml", ".sh", ".md", ".json", ".txt", ".ini", ".cfg", ".env"}
# Fichiers racine toujours inclus (même sans extension reconnue)
ALWAYS_INCLUDE = {"run.py", "run.sh", "pyproject.toml", "README.md", "requirements.txt", "Makefile"}
# Exclusions (répertoires et fichiers)
EXCLUDE_DIRS = {".venv", ".git", "__pycache__", "data", "logs", "node_modules", ".idea", "build", "dist", ".hermes", "assets", "icons", "img"}
EXCLUDE_FILES = {
    "NURU_CODE_CONCATENATED.txt", "NURU_CODE_EXPERTS_2026-08-06.txt",
    "PROBLEMES_NURU.md",  # référencé séparément (le lecteur doit l'avoir en main)
}
EXCLUDE_SUFFIX = {".safetensors", ".bin", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".wav", ".mp3", ".ttf", ".otf", ".db", ".sqlite", ".pyc", ".so", ".dylib", ".qss", ".woff", ".woff2", ".pdf", ".docx", ".xlsx"}
MAX_FILE_LINES = 60_000  # garde-fou anti-fichier monstrueux


def git(*args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=30)
        return r.stdout
    except Exception:
        return ""


def collect_files() -> list[Path]:
    files: list[Path] = []
    # Racine
    for f in sorted(ROOT.iterdir()):
        if f.is_file() and (f.name in ALWAYS_INCLUDE or f.suffix in INCLUDE_EXT):
            if f.name not in EXCLUDE_FILES and f.suffix not in EXCLUDE_SUFFIX:
                files.append(f)
    # src/ et config/
    for sub in ("src", "config"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for root, dirs, fnames in os.walk(d):
            dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
            for fn in sorted(fnames):
                p = Path(root) / fn
                if p.suffix not in INCLUDE_EXT or p.suffix in EXCLUDE_SUFFIX:
                    continue
                if p.name in EXCLUDE_FILES:
                    continue
                files.append(p)
    # Filtre : ligne max
    files = [p for p in files if _line_count(p) <= MAX_FILE_LINES]
    return files


def _line_count(p: Path) -> int:
    try:
        with open(p, "r", errors="replace") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def header() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    branch = git("branch", "--show-current").strip()
    commit = git("log", "-1", "--format=%h %s").strip()
    return (
        "# ═══════════════════════════════════════════════════════════════════════\n"
        f"#  NURU — CODE SOURCE COMPLET (audit experts externes)\n"
        f"#  Généré le {now} | branche: {branch} | HEAD: {commit}\n"
        f"#  Lire AVEC : PROBLEMES_NURU.md (10 réflexions R1-R10 + questions ouvertes)\n"
        "# ═══════════════════════════════════════════════════════════════════════\n"
        "#\n"
        "#  CONTENU : 100% des fichiers source (aucune sélection).\n"
        "#  Les experts sont invités à chercher ce que l'assistant a pu RATER :\n"
        "#  la table des matières reflète l'arborescence réelle, pas un choix.\n"
        "#\n"
    )


def toc(files: list[Path]) -> str:
    lines = ["# ── TABLE DES MATIÈRES ──\n"]
    for i, p in enumerate(files, 1):
        rel = p.relative_to(ROOT)
        n = _line_count(p)
        lines.append(f"# {i:4d}. {rel}  ({n} lignes)")
    lines.append(f"#\n# Total: {len(files)} fichiers")
    return "\n".join(lines) + "\n"


def file_block(p: Path, idx: int) -> str:
    rel = p.relative_to(ROOT)
    n = _line_count(p)
    status = ""
    st = git("status", "--porcelain", "--", str(rel)).strip()
    if st:
        # Codes git : ' M' = modifié non indexé, 'M ' = indexé, 'MM' = les deux, '??' = non suivi
        code = st[:2].replace(" ", "")
        if code.startswith("M") or code.startswith("A"):
            status = "  [⚠️ MODIFIÉ NON COMMITÉ]"
    sep = "═" * 78
    try:
        content = p.read_text(errors="replace")
    except Exception as e:
        content = f"# (illisible: {e})"
    return (
        f"\n\n{'#' + sep}\n"
        f"# FICHIER {idx:4d} : {rel}{status}\n"
        f"# {n} lignes\n"
        f"{'#' + sep}\n"
        f"{content}\n"
    )


def main() -> None:
    files = collect_files()
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(header())
        fh.write(toc(files))
        for i, p in enumerate(files, 1):
            fh.write(file_block(p, i))
        # Section finale : diff non commité
        diff = git("diff", "--stat")
        if diff.strip():
            fh.write(f"\n\n{'#' + '═' * 78}\n# SECTION FINALE — MODIFICATIONS NON COMMITÉES (git diff)\n{'#' + '═' * 78}\n\n")
            fh.write(diff)
            full = git("diff")
            if len(full) < 400_000:
                fh.write("\n\n── DIFF COMPLET ──\n\n")
                fh.write(full)
        # git log récent
        log = git("log", "--oneline", "-25")
        if log.strip():
            fh.write(f"\n\n{'#' + '═' * 78}\n# SECTION FINALE — HISTORIQUE RÉCENT (git log -25)\n{'#' + '═' * 78}\n\n")
            fh.write(log)
    size_mb = OUT.stat().st_size / 1_048_576
    print(f"✅ {OUT.name}")
    print(f"   Fichiers: {len(files)} | Taille: {size_mb:.1f} Mo | Lignes: {sum(_line_count(p) for p in files)}")


if __name__ == "__main__":
    main()
