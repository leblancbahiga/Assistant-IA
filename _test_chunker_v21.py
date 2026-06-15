#!/usr/bin/env python3
"""Test du chunker V2.1 corrigé sur un document réel."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)

from src.rag.v2_chunking import HierarchicalChunkerV2
from src.ingestion import IngestionEngine

engine = IngestionEngine()

# Test sur le fichier Sustainable Agriculture
test_file = "/Users/leblancbahiga/Documents/YARID/reports field/Sustainable -Agriculture Monitoring tool.docx"
print(f"=== TEST CHUNKER V2.1 ===")
print(f"Fichier: {test_file}")

text = engine._parse_file(test_file)
print(f"Texte extrait: {len(text)} chars")

# Ancien chunking
from src.rag.v2_chunking import HierarchicalChunkerV2 as OldChunker
old = OldChunker("rapport")
old_chunks = old.chunk(text, source=os.path.basename(test_file), doc_title=os.path.basename(test_file))

print(f"\nAVEC L'ANCIEN CHUNKER:")
for c in old_chunks:
    d = c.to_dict()
    print(f"  Chunk: {d['content'][:80]}... ({c.char_count} chars)")

# Nouveau chunking — même classe (nous avons patché le même fichier)
# Les correctifs sont déjà appliqués.
print(f"\nAVEC LE CHUNKER V2.1 (patch déjà actif):")
for c in old_chunks:
    d = c.to_dict()
    print(f"  Chunk: {d['content'][:80]}... ({c.char_count} chars)")

print(f"\nRÉSUMÉ:")
print(f"  Ancien: {len(old_chunks)} chunks, taille moyenne: {sum(c.char_count for c in old_chunks)/len(old_chunks):.0f} chars")
print(f"  Nouveau: {len(old_chunks)} chunks (même classe)")

# Maintenant testons un PDF
print(f"\n\n=== TEST SUR DOCUMENT PLUS LARGE ===")
test_pdf = "/Users/leblancbahiga/Documents/YARID/reports field/2023.Project progress report.xlsx"
print(f"Pas un PDF, testons un vrai PDF...")
# Trouvons un PDF dans le corpus
import glob
pdfs = []
for dirname in ["Documents", "Desktop", "Downloads"]:
    base = os.path.expanduser(f"~/{dirname}")
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.endswith('.pdf'):
                    pdfs.append(os.path.join(root, f))
                    if len(pdfs) >= 3:
                        break
            if len(pdfs) >= 3:
                break
    if len(pdfs) >= 3:
        break

for pdf in pdfs:
    print(f"\n--- {os.path.basename(pdf)} ---")
    try:
        txt = engine._parse_file(pdf)
        print(f"  Texte: {len(txt)} chars")
        if len(txt) < 100:
            print(f"  (trop court, skip)")
            continue
        
        profile = HierarchicalChunkerV2.detect_profile(os.path.basename(pdf))
        print(f"  Profil: {profile}")
        chunker = HierarchicalChunkerV2(profile=profile)
        chunks = chunker.chunk(txt, source=os.path.basename(pdf), doc_title=os.path.basename(pdf))
        
        print(f"  Chunks: {len(chunks)}")
        for c in chunks:
            print(f"    Level={c.level} | {c.char_count:>5} chars | {c.content[:100]}...")
        
        avg = sum(c.char_count for c in chunks) / len(chunks) if chunks else 0
        print(f"  Moyenne: {avg:.0f} chars")
        big = [c for c in chunks if c.char_count > 5000]
        print(f"  > 5000 chars: {len(big)}/{len(chunks)}")
    except Exception as e:
        print(f"  ❌ ERREUR: {e}")
