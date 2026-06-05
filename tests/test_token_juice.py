"""Tests unitaires pour TokenJuice."""
import sys; sys.path.insert(0, 'src')
from token_juice import (
    TokenJuice, _dedup_consecutive, _crush_logs,
    _crush_timestamps, _shrink_urls, _shrink_paths,
    _strip_html, _token_truncate,
)

juice = TokenJuice(enabled=True)
errors = []

def check(name, cond, msg=""):
    if not cond:
        errors.append(f"❌ {name}: {msg}")
        print(f"❌ {name}: {msg}")
    else:
        print(f"  ✅ {name}")

# Test URL longue
text1 = "Regarde https://github.com/very-long-repository-name-with-many-subdirectories/blob/main/src/test.py"
r1 = juice.compress(text1)
check("URL shrink", len(r1) < len(text1), f"{len(text1)}→{len(r1)}")
check("URL preserves prefix", "Regarde" in r1, repr(r1))

# Test timestamp
text2 = "Date: 2024-06-05T14:30:22.123Z et 2026-06-05 09:45:00"
r2 = juice.compress(text2)
check("Timestamp crush", "[TS]" in r2, repr(r2))
check("Timestamp preserves text", "Date:" in r2, repr(r2))

# Test logs (post-stage seulement)
text3 = "DEBUG: loading model\nINFO: loaded\nWARNING: low mem\nIMPORTANT: keep me"
r3 = juice.compress(text3, stage="post")
check("Log crush keeps important", "IMPORTANT: keep me" in r3, repr(r3))
check("Log crush removes DEBUG", "DEBUG" not in r3, repr(r3))

# Test logs pre-stage (ne doit PAS enlever les logs)
r3_pre = juice.compress(text3, stage="pre")
check("Log crush pre-stage OK", "DEBUG" in r3_pre, repr(r3_pre))

# Test dédup (texte assez long pour passer le seuil)
text4 = "a\na\na\nb\nb\nc\n"
text4 += "d\nd\nd\ne\nf\nf\n"
r4 = juice.compress(text4)
check("Dedup reduces count", r4.count("\n") + 1 < 12, f"{r4.count(chr(10))+1} lignes")
check("Dedup preserves unique", all(c in r4 for c in "abcdef"), repr(r4))

# Test HTML
text5 = "<div><h1>Titre</h1><p>Texte <b>gras</b></p><ul><li>A</li><li>B</li></ul></div>"
r5 = juice.compress(text5)
check("HTML content preserved", "Titre" in r5 and "A" in r5, repr(r5))
check("HTML tags stripped", "<" not in r5, repr(r5))

# Test chunks (troncature + compression)
chunks = ["A" * 3000, "B" * 3000]
r6 = juice.compress_chunks(chunks)
check("Chunks compress < 4100", len(r6) < 4100, f"{len(r6)}")

# Test query compress (requête longue avec date)
r7 = juice.compress_query(
    "Quelle est la météo à Kinshasa le 2024-06-05? " * 5
)
check("Query compress DATE", "[DATE]" in r7, repr(r7[:100]))
check("Query shorter", len(r7) < 250, f"{len(r7)}")

# Test court
check("Short text unchanged", juice.compress("Salut") == "Salut")

# Test vide
check("Empty text", juice.compress("") == "")

# Test stats
check("Stats compressions > 0", juice.stats["compressions"] > 0)

# Test désactivé
juice2 = TokenJuice(enabled=False)
check("Disabled noop", juice2.compress("long " * 100) == "long " * 100)

# Test troncature
check("Token truncate ~2000 chars", len(_token_truncate("A" * 5000)) <= 2020)

# Test path shrink (2 segments longs consécutifs)
path_test = "dans /very-long-project-name-12345/very-long-folder-name-67890/"
r_path = _shrink_paths(path_test)
check("Path shrink 2 segments", len(r_path) < len(path_test), repr(r_path))

# Test path court (1 segment court) — pas de changement
path_short = "chemin /Users/leb/projets/"
r_path_short = _shrink_paths(path_short)
check("Path court unchanged", r_path_short == path_short, repr(r_path_short))

# Résumé
print()
if errors:
    print(f"❌ {len(errors)} échec(s):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("✅ Tous les tests TokenJuice passés !")
