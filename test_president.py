"""Test NURU : pose une question d'actualité pour vérifier le passage du contexte web au cloud."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from src.nuru_core import NuruCore

async def main():
    print("🚀 Initialisation de NURU...")
    core = NuruCore()
    core.start_background_tasks()
    
    question = "Qui est l'actuel président des États-Unis ?"
    print("\n" + "=" * 60)
    print(f"Q: {question}")
    print("=" * 60)
    
    try:
        response = ""
        async for token in core.process_query_v45(question):
            response += token
            print(token, end="", flush=True)
        
        print("\n\n" + "=" * 60)
        # Vérifier si la réponse mentionne Trump (correct) ou Biden (obsolète)
        if "trump" in response.lower():
            print("✅ NURU répond correctement : Donald Trump")
        elif "biden" in response.lower():
            print("⚠️ NURU répond encore Joe Biden — problème de contexte web")
        else:
            print("ℹ️ Réponse ni Trump ni Biden — vérifier le contenu")
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
