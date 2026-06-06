"""
NURU V6 — Ré-indexation ultra-ciblée.
Seulement les CV + lettres de motivation de Leblanc.
"""
import sys
import os
import hashlib
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import config
from src.rag_engine import RAGEngine
from src.embedder import Embedder
from src.profile_boost import is_owner_document, get_boost_score

# Fichiers PERSONNELS de Leblanc — whitelist exacte
PERSONAL_FILES = [
    # CV
    "2 - CV_2024-10-11_Leblanc_BAHIGA Mudarhi.pdf",
    "CV_Leblanc_BAHIGA_2026.docx",
    "CV Leblanc (4).pdf",
    "CV Bahiga_Leblanc.pdf",
    "CV_Bahiga_Leblanc.pdf",
    "CV_Bahiga_Leblanc_English.docx",
    "CV_2026-03-23_Leblanc_BAHIGA Mudarhi.pdf",
    "cv_english.pdf",
    # Lettres de motivation
    "lettre de motivation 013_KIN_2023_charge_de_projet_agriculture.pdf",
    "CL_Bahiga_Leblanc.pdf",
    "CL_Bahiga_Leblanc_opt.pdf",
    "Motivation_Ass_resilience_PAM.docx",
    "Motivation_Chef_de _projet_pont_de_lhumanite.docx",
    "Motivation_C4D_Enabel.docx",
    "Motivation_Expert_developpement_communautaire_Star_est.docx",
    "Motivation_Spécialiste_en_Stratégie_Semencière.docx",
    # Attestations
    "ATTESTATION DE SERVICE RENDU LEBLANC.pdf",
    "Ref_Bahiga_Leblanc.docx",
    # Profil
    "Leblanc BAHIGA MUDARHI.docx",
    "Leblanc BAHIGA Mudarhi.docx",
    "Profile.pdf",
]

DOCUMENTS_DIR = Path.home() / "Documents"


async def index_personal():
    print("=" * 60)
    print("📚 NURU V6 — Indexation ciblée (whitelist)")
    print(f"   {len(PERSONAL_FILES)} fichiers ciblés")
    print("=" * 60)

    rag = RAGEngine()
    embedder = Embedder()
    
    from src.rag.v2_chunking import HierarchicalChunkerV2
    chunker = HierarchicalChunkerV2()

    total = 0
    found = 0

    for fname in PERSONAL_FILES:
        # Chercher le fichier dans Documents (récursif)
        fpath = None
        for root, _, files in os.walk(DOCUMENTS_DIR):
            if fname in files:
                fpath = Path(root) / fname
                break
        
        if not fpath or not fpath.exists():
            print(f"  ⏭️  {fname} — introuvable")
            continue

        found += 1
        ext = fpath.suffix.lower()
        
        print(f"  📄 {fname}...", end=" ")
        
        try:
            # Parser
            text = ""
            if ext == ".txt" or ext == ".md":
                text = fpath.read_text(encoding="utf-8", errors="replace")
            elif ext == ".pdf":
                import fitz
                with fitz.open(str(fpath)) as doc:
                    text = "\n".join(page.get_text() for page in doc)
            elif ext == ".docx":
                from docx import Document
                doc = Document(str(fpath))
                text = "\n".join(p.text for p in doc.paragraphs)
            else:
                print("⏭️  format non supporté")
                continue

            if not text or len(text) < 100:
                print("⏭️  vide")
                continue

            # Chunking V2
            v2_chunks = chunker.chunk(text, source=fname, doc_title=fname)
            if not v2_chunks:
                print("⏭️  aucun chunk")
                continue

            # V6.2 : Vérifier le hash avant d'indexer (déduplication)
            file_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
            if rag.is_file_up_to_date(str(fpath), 0, file_hash):
                print(f"⏭️ déjà indexé (hash: {file_hash[:12]}...)")
                continue
            
            # Embedding par lots pour économiser les appels MLX
            chunks_to_index = []
            for c in v2_chunks:
                content = c.to_dict()["content"]
                # Batch embedding
                embeddings = await embedder.embed([content], is_query=False)
                chunks_to_index.append({
                    "content": content,
                    "source": fname,
                    "embedding": embeddings[0],
                    "date": "",
                    "title": c.section_title or c.doc_title,
                    "level": c.level,
                })

            rag.add_chunks(chunks_to_index)
            rag.mark_file_indexed(str(fpath), 0, file_hash)
            total += len(chunks_to_index)
            print(f"✅ {len(chunks_to_index)} chunks")
            
        except Exception as e:
            print(f"❌ {e}")

    print("\n" + "=" * 60)
    print(f"✅ Terminé: {found}/{len(PERSONAL_FILES)} fichiers trouvés, {total} chunks")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(index_personal())
