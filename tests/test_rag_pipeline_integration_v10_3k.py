"""Test B-RAG-Pipeline — Audit 2026-06-14.

Le LLM reçoit 'je n'ai pas d'informations sur Leblanc Bahiga' alors que le
RAG contient bien [CV_2024-04-16_Leblanc_BAHIGA (1).pdf] Leblanc BAHIGA / INGENIEUR AGRONOME.

Pipeline à vérifier :
1. RAGEngine.retrieve(query) → retourne 3303 chars (top_score=0.33)
2. RetrievePrimary.retrieve_primary(query) → appelle RAGEngine.retrieve
3. RagPipeline._retrieve_one() OU via boucle retrieve_multi → doit conserver 3303 chars
4. Orchestrator._build_prompt() avec rag_context=3303 chars → prompt final contient l'info
5. LLM reçoit le prompt final → doit pouvoir répondre
"""
import asyncio
import sys
sys.path.insert(0, '/Users/leblancbahiga/Downloads/Assistant IA')

from src.rag_engine import RAGEngine
from src.orchestration.rag_pipeline import RAGOrchestrator


def test_retrieve_primary_returns_full_context():
    """retrieve_primary retourne bien la string context (pas un unpack cassé)."""
    async def go():
        re = RAGEngine()
        ro = RAGOrchestrator(
            rag_engine=re, cloud_llm=None, web_search=None,
            event_bus=None, response_guard=None, evidence_verifier=None,
        )
        ctx, result = await ro.retrieve_primary("Qui est Leblanc Bahiga ?", None)
        assert isinstance(ctx, str), f"ctx doit être str, got {type(ctx).__name__}"
        assert len(ctx) > 100, (
            f"ctx trop court ({len(ctx)} chars). Bug unpack: "
            f"`rag_ctx, result = primary_rag_context` tronquait à 2 chars."
        )
        # Le CV doit être présent
        assert "Leblanc" in ctx or "BAHIGA" in ctx, (
            f"Contexte RAG ({len(ctx)} chars) ne contient pas 'Leblanc' : {ctx[:200]}"
        )
        return ctx
    ctx = asyncio.run(go())
    print(f"  retrieve_primary OK : {len(ctx)} chars")


def test_retrieve_multi_preserves_primary_context():
    """retrieve_multi ne doit PAS tronquer le primary_rag_context."""
    async def go():
        re = RAGEngine()
        ro = RAGOrchestrator(
            rag_engine=re, cloud_llm=None, web_search=None,
            event_bus=None, response_guard=None, evidence_verifier=None,
        )
        primary_ctx, primary_result = await ro.retrieve_primary("Qui est Leblanc Bahiga ?", None)
        # Cas intent="RAG" : retrieve_multi doit retourner le primary context UNCHANGED
        out_ctx, out_web, out_result = await ro.retrieve_multi(
            query="Qui est Leblanc Bahiga ?",
            intent="RAG",
            primary_rag_context=primary_ctx,
            primary_rag_result=primary_result,
        )
        assert isinstance(out_ctx, str), f"out_ctx doit être str, got {type(out_ctx).__name__}"
        assert out_ctx == primary_ctx, (
            f"retrieve_multi a MODIFIÉ le context !\n"
            f"  Avant: {len(primary_ctx)} chars\n"
            f"  Après: {len(out_ctx)} chars\n"
            f"  Bug unpack suspect : la chaîne a été tronquée."
        )
    asyncio.run(go())
    print("  retrieve_multi OK : primary context unchanged")


def test_full_orchestrator_query_has_rag_context():
    """Test E2E : l'orchestrator complet envoie un prompt contenant la doc utilisateur."""
    from src.nuru_core import NuruCore

    captured_prompt = []

    async def go():
        core = NuruCore()

        # Capturer le full_prompt envoyé au LLM via llm_gen.generate
        # V10.3j+ : process_query utilise self.llm_gen.generate (LLMGenerator)
        # au lieu d'un _generate inline.
        orig_generate = core.orchestrator.llm_gen.generate

        async def spy_generate(*args, **kwargs):
            # Signature LLMGenerator.generate(system_prompt, full_prompt, query, intent, ctx, ...)
            if len(args) >= 2:
                sysp, fullp = args[0], args[1]
                captured_prompt.append(fullp)
            async for tok in orig_generate(*args, **kwargs):
                yield tok

        core.orchestrator.llm_gen.generate = spy_generate

        out = []
        async for tok in core.process_query("Qui est Leblanc Bahiga ?"):
            out.append(tok)
        return core

    core = asyncio.run(go())

    assert len(captured_prompt) > 0, "Aucun prompt capturé (orchestrator pas appelé ?)"
    full_prompt = captured_prompt[0]
    assert "Leblanc" in full_prompt or "BAHIGA" in full_prompt, (
        f"PROMPT FINAL ne contient pas 'Leblanc'.\n"
        f"Taille prompt: {len(full_prompt)} chars\n"
        f"Prompt (300 premiers chars): {full_prompt[:300]}\n"
        f"...\n"
        f"Prompt (50 derniers chars): {full_prompt[-50:]}\n"
        f"NB : si prompt vide/tiny, le bug est dans retrieve_multi ou _build_prompt."
    )
    print(f"  E2E OK : prompt final contient 'Leblanc' sur {len(full_prompt)} chars total")
