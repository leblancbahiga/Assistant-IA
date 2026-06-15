#!/usr/bin/env python3
"""Test retrieval quality of RAG engine."""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
logging.disable(logging.CRITICAL)
import asyncio

from src.rag_engine import RAGEngine

async def test():
    engine = RAGEngine()
    
    tests = [
        "Sustainable agriculture training YARID",
        "CV Leblanc Bahiga",
        "LEAD Achievements YARID",
        "rapport BEACCOM riz Walikale",
        "What is NURU assistant",
        "Sustainable Agriculture Monitoring tool",
        "YARID concept note training",
    ]
    
    for query in tests:
        print(f"\n{'='*60}")
        print(f"QUERY: {query}")
        print(f"{'='*60}")
        
        try:
            ctx, res = await engine.retrieve(query)
            
            print(f"  Top score:    {res.top_score:.3f}" if res and hasattr(res, 'top_score') else f"  Top score:    N/A")
            print(f"  Confidence:   {res.confidence_label}" if res and hasattr(res, 'confidence_label') else f"  Confidence:   N/A")
            print(f"  Context len:  {len(ctx)} chars")
            print(f"  Chunks:       {res.chunks_retrieved}" if res and hasattr(res, 'chunks_retrieved') else f"  Chunks:       N/A")
            
            if hasattr(res, 'rejection_reason') and res.rejection_reason:
                print(f"  REJECTED:     {res.rejection_reason}")
            if hasattr(res, 'all_scores') and res.all_scores:
                print(f"  All scores:   {[f'{s:.3f}' for s in res.all_scores[:5]]}")
            
            if ctx:
                # Show source of first result
                sources = []
                for line in ctx.split('\n'):
                    if line.startswith('[SOURCE') and ']' in line:
                        sources.append(line)
                if sources:
                    print(f"  Sources found:")
                    for s in sources[:3]:
                        print(f"    {s}")
                print(f"  Preview:      {ctx[:200]}...")
            else:
                print(f"  ❌ EMPTY — No context returned!")
                print(f"  Scores: {[f'{s:.3f}' for s in res.all_scores[:5]]}" if hasattr(res, 'all_scores') and res.all_scores else "  No scores")
        except Exception as e:
            import traceback
            print(f"  ❌ ERROR: {e}")
            traceback.print_exc()

asyncio.run(test())
