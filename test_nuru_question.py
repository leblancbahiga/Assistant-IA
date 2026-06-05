"""Test NURU : pose 'Qui es-tu?' et affiche la réponse."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import config
from src.core.events import EventBus
from src.core.orchestrator import NuruOrchestrator
from src.core.router import Router
from src.semantic_router import SemanticRouter
from src.core.policies import PolicyEngine
from src.core.response_guard import StrictRAGGuard
from src.ai.verifier import EvidenceVerifier
from src.memory_store import MemoryStore


async def main():
    # Minimal init
    event_bus = EventBus()
    memory = MemoryStore()
    policy = PolicyEngine()
    router = Router()
    guard = StrictRAGGuard("hybrid")
    verifier = EvidenceVerifier()

    # Mock RAG / LLM pour voir le routage seul
    class MockRAG:
        async def retrieve(self, q):
            return ("", type("R", (), {"top_score": 0.0, "chunks_retrieved": 0, "sources": []})())

    orchestrator = NuruOrchestrator(
        router=router,
        rag_engine=MockRAG(),
        local_llm=None,
        cloud_llm=None,
        memory_store=memory,
        policy_engine=policy,
        event_bus=event_bus,
    )

    # Tester le routage
    print("=" * 60)
    print("🧪 Test : 'Qui es-tu?'")
    print("=" * 60)
    
    is_online = await orchestrator._check_connectivity()
    print(f"📡 Connectivité : {'✅ En ligne' if is_online else '❌ Hors-ligne'}")
    
    ctx = orchestrator._build_query_context("Qui es-tu?", "test_session", is_online)
    from src.core.query_context import QueryContext
    # Actually let me just check what the router decides
    
    from src.core.query_context import QueryContext
    ctx = QueryContext.from_runtime("Qui es-tu?", "test_session", is_online=is_online)
    route_result = await router.route_with_context(ctx)
    print(f"🧠 Route décidée: {route_result.decision} (confiance: {route_result.confidence})")
    print(f"   Raison: {route_result.reasoning}")
    print(f"   Score RAG: {route_result.rag_top_score}")

    # Test RAG keywords
    from src.semantic_router import RAG_KEYWORDS
    q = "Qui es-tu?".lower()
    has_rag = any(kw in q for kw in RAG_KEYWORDS)
    print(f"📄 Mots-clés RAG: {'OUI' if has_rag else 'NON'}")
    
    from src.semantic_router import WEB_TRIGGERS, TRIVIAL_PATTERNS
    import re
    is_trivial = any(re.match(p, q) for p in TRIVIAL_PATTERNS)
    has_web = any(t in q for t in WEB_TRIGGERS)
    print(f"💬 Trivial: {'OUI' if is_trivial else 'NON'}")
    print(f"🌐 Web trigger: {'OUI' if has_web else 'NON'}")


if __name__ == "__main__":
    asyncio.run(main())
