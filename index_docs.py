"""Indexe les fichiers de Documents/ et Desktop/ dans le RAG de NURU."""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS
from src.config import config

async def main():
    core = IngestionEngine()
    
    dirs = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
    ]
    
    # Collecter tous les fichiers
    all_files = []
    for base_dir in dirs:
        if not base_dir.exists():
            print(f"❌ {base_dir} n'existe pas")
            continue
        for root, _, files in os.walk(base_dir):
            for f in files:
                if any(f.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                    all_files.append(os.path.join(root, f))
    
    print(f"📂 {len(all_files)} fichiers trouvés (PDF, DOCX, TXT, MD, CSV, JSON)")
    print(f"   Exclusions : .git, __pycache__, .venv, node_modules")
    
    # Filtrer les exclusions
    exclude_dirs = {'.git', '__pycache__', '.venv', 'node_modules', '.idea', '.DS_Store'}
    filtered = [f for f in all_files if not any(
        excl in Path(f).parts for excl in exclude_dirs
    )]
    
    print(f"📄 {len(filtered)} fichiers à indexer")
    
    success = 0
    errors = 0
    skipped = 0
    
    for i, fp in enumerate(filtered):
        # Vérifier si déjà indexé
        fsize = os.path.getsize(fp)
        if fsize > 10 * 1024 * 1024:  # > 10MB
            print(f"  ⏭️  [{i+1}/{len(filtered)}] Trop gros ({fsize/1024/1024:.0f}MB): {Path(fp).name}")
            skipped += 1
            continue
        
        try:
            await core.index_file(fp)
            print(f"  ✅ [{i+1}/{len(filtered)}] {Path(fp).name}")
            success += 1
        except Exception as e:
            print(f"  ❌ [{i+1}/{len(filtered)}] {Path(fp).name}: {e}")
            errors += 1
        
        # Petite pause entre chaque fichier pour le CPU
        await asyncio.sleep(0.2)
    
    print("\n" + "=" * 50)
    print(f"✅ Indexation terminée :")
    print(f"   ✅ {success} fichiers indexés")
    print(f"   ⏭️  {skipped} fichiers ignorés (>10MB)")
    print(f"   ❌ {errors} erreurs")
    
    # Afficher le résultat final
    import pysqlite3 as sqlite3
    import sqlite_vec
    conn = sqlite3.connect(str(config.index_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    count = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    sources = conn.execute('SELECT COUNT(DISTINCT source) FROM chunks').fetchone()[0]
    print(f"\n📊 Index maintenant : {count} chunks ({sources} sources)")
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
