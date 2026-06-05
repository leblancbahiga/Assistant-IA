"""Test NURU : pose 'Qui es-tu?' via NuruCore."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.nuru_core import NuruCore
from src.config import config

async def main():
    print("🚀 Initialisation de NURU...")
    core = NuruCore()
    core.start_background_tasks()
    
    print("\n" + "=" * 60)
    print("Q: Qui es-tu?")
    print("=" * 60)
    
    try:
        response = ""
        async for token in core.process_query_v45("Qui es-tu?"):
            response += token
        
        print(f"\nR: {response}")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
