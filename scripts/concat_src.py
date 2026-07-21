#!/usr/bin/env python3
"""Concatène tous les fichiers source de src/ en un seul fichier pour LLM.

Usage:
    python scripts/concat_src.py [--output chemin] [--no-token-count]

Options:
    --output, -o    Fichier de sortie (défaut: concat_src_output.txt)
    --no-token-count  Pas d'estimation du nombre de tokens
"""

import os, sys, argparse
from pathlib import Path

# Extensions à inclure
INCLUDE_EXTENSIONS = {'.py', '.md', '.json', '.yaml', '.yml', '.toml', '.cfg', '.txt', '.css', '.qss', '.html'}
# Exclusions (noms de fichiers/dossiers)
EXCLUDE_NAMES = {'__pycache__', '.DS_Store', '*.pyc', '__init__.py', '.git'}
# Taille max par fichier (500KB)
MAX_FILE_SIZE = 500 * 1024


def collect_files(src_dir: Path) -> list[Path]:
    files = []
    for root, dirs, filenames in os.walk(src_dir):
        # Exclure __pycache__ et autres dossiers cachés
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for f in sorted(filenames):
            fpath = Path(root) / f
            ext = fpath.suffix.lower()
            if ext in INCLUDE_EXTENSIONS and fpath.stat().st_size <= MAX_FILE_SIZE:
                files.append(fpath)
    return files


def estimate_tokens(text: str) -> int:
    """Estimation grossière : ~4 caractères par token."""
    return len(text) // 4


def main():
    parser = argparse.ArgumentParser(description='Concatène les fichiers src/ pour LLM')
    parser.add_argument('--output', '-o', default='concat_src_output.txt',
                        help='Fichier de sortie (défaut: concat_src_output.txt)')
    parser.add_argument('--no-token-count', action='store_true',
                        help='Ne pas afficher l\'estimation de tokens')
    args = parser.parse_args()

    src_dir = Path(__file__).resolve().parent.parent / 'src'
    if not src_dir.exists():
        print(f"❌ src/ introuvable : {src_dir}")
        sys.exit(1)

    files = collect_files(src_dir)
    total_tokens = 0
    total_chars = 0
    n_files = len(files)

    with open(args.output, 'w', encoding='utf-8') as out:
        out.write(f"# CONCATÉNATION SOURCE — NURU\n")
        out.write(f"# {n_files} fichiers depuis {src_dir}\n")
        out.write(f"# Généré le {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        out.write("#" * 60 + "\n\n")

        for fpath in files:
            rel = fpath.relative_to(src_dir.parent)
            content = fpath.read_text(encoding='utf-8', errors='replace')
            n_lines = content.count('\n') + 1

            out.write(f"{'='*60}\n")
            out.write(f"# FICHIER: {rel}\n")
            out.write(f"# LIGNES: {n_lines}  |  CARACTÈRES: {len(content)}\n")
            out.write(f"{'='*60}\n\n")
            out.write(content)
            out.write("\n\n")

            total_chars += len(content)

        if not args.no_token_count:
            total_tokens = total_chars // 4
            out.write(f"\n# STATISTIQUES FINALES\n")
            out.write(f"# Fichiers: {n_files}\n")
            out.write(f"# Caractères: {total_chars:,}\n")
            out.write(f"# Tokens (estimés): {total_tokens:,}\n")

    size_kb = Path(args.output).stat().st_size / 1024
    print(f"✅ {n_files} fichiers → {args.output}")
    print(f"   Taille: {size_kb:.0f} Ko")
    if not args.no_token_count:
        print(f"   Tokens estimés: {total_tokens:,}")


if __name__ == '__main__':
    main()
