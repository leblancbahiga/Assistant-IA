#!/usr/bin/env python3
"""Évaluation RAG — NURU V6
Mesure objective de la qualité de récupération des documents.
Usage: python3 tests/eval_rag.py
"""
import sys
import os
import yaml
import json
import time
from pathlib import Path
from statistics import mean

# Ajouter la racine du projet au path (src.xxx imports)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["TOKENIZERS_PARALLELISM"] = "false"

DATASET_PATH = Path(__file__).parent / "rag_eval_dataset.yaml"


def load_dataset(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_rag(dataset: list[dict]) -> dict:
    """Évalue le RAG sur le dataset."""
    from src.rag_engine import RAGEngine
    import asyncio

    async def _run():
        engine = RAGEngine()

        results = []
        total_recall = 0
        total_precision = 0
        total_latency = 0

        print(f"\n{'='*60}")
        print(f"📊 ÉVALUATION RAG — {len(dataset)} questions")
        print(f"{'='*60}\n")

        for idx, item in enumerate(dataset, 1):
            question = item["question"]
            expected_source = item["expected_source"]
            expected_keywords = item["expected_keywords"]

            t0 = time.time()

            # Recherche RAG : retrieve() retourne (contexte_str, RAGResult)
            context, rag_result = await engine.retrieve(question, k=5)

            latency = time.time() - t0
            total_latency += latency

            # Les chunks sont dans rag_result.sources (list[dict])
            sources = rag_result.sources if hasattr(rag_result, 'sources') else []
            sources_found = [s.get("name", "") for s in sources]
            source_recalled = any(expected_source in s for s in sources_found)

            # Vérifier les mots-clés dans le contexte complet formaté
            all_text = context.lower()
            keywords_present = []
            keywords_missing = []
            for kw in expected_keywords:
                if kw.lower() in all_text:
                    keywords_present.append(kw)
                else:
                    keywords_missing.append(kw)

            keyword_precision = len(keywords_present) / len(expected_keywords) if expected_keywords else 0
            scores = [s.get("score", 0) or 0 for s in sources]

            results.append({
            "question": question,
            "source_recalled": source_recalled,
            "keyword_precision": keyword_precision,
            "scores": scores,
                "latency": latency,
                "keywords_present": keywords_present,
                "keywords_missing": keywords_missing,
                "sources_found": sources_found,
            })

            total_recall += 1 if source_recalled else 0
            total_precision += keyword_precision

            # Affichage
            status = "✅" if source_recalled else "❌"
            kw_status = f"{len(keywords_present)}/{len(expected_keywords)}"
            avg_score = mean(scores) if scores else 0

            # Truncate question for display
            q_display = question if len(question) < 55 else question[:52] + "..."
            print(f"  {idx:2d}. {status} {q_display}")
            print(f"       Source: {'✓' if source_recalled else '✗'}  |  Mots-clés: {kw_status}  |  Score: {avg_score:.2f}  |  Latence: {latency:.1f}s")
            if keywords_missing:
                print(f"       ⚠️  Manquants: {keywords_missing}")

        # Synthèse
        n = len(dataset)
        recall_at_5 = total_recall / n * 100 if n else 0
        avg_precision = total_precision / n * 100 if n else 0
        avg_latency = total_latency / n if n else 0

        print(f"\n{'='*60}")
        print(f"📈 RÉSULTATS")
        print(f"{'='*60}")
        print(f"  Recall@5:        {recall_at_5:.1f}%  ({total_recall}/{n})")
        print(f"  Précision mots-clés: {avg_precision:.1f}%")
        print(f"  Latence moyenne:  {avg_latency:.2f}s")
        print(f"  Score RAG moyen:  {mean([mean(r['scores']) if r['scores'] else 0 for r in results]):.2f}")
        print(f"{'='*60}\n")

        return {
            "recall_at_5": recall_at_5,
            "avg_precision": avg_precision,
            "avg_latency": avg_latency,
            "n": n,
            "results": results,
        }

    return asyncio.run(_run())


if __name__ == "__main__":
    if not DATASET_PATH.exists():
        print(f"❌ Dataset introuvable : {DATASET_PATH}")
        print("   Créez d'abord tests/rag_eval_dataset.yaml avec 20-30 questions")
        sys.exit(1)

    dataset = load_dataset(DATASET_PATH)
    print(f"📂 Dataset chargé : {len(dataset)} questions")

    # Filtre optionnel par type de document
    if len(sys.argv) > 1:
        doc_type = sys.argv[1]
        dataset = [q for q in dataset if q.get("doc_type") == doc_type]
        print(f"   Filtre: doc_type={doc_type} → {len(dataset)} questions")

    results = evaluate_rag(dataset)

    # Sauvegarder les résultats
    out_path = DATASET_PATH.with_suffix(".results.json")
    with open(out_path, "w") as f:
        # Nettoyer les résultats pour le JSON (enlever les sérialisations complexes)
        clean = {k: v for k, v in results.items() if k != "results"}
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print(f"💾 Résultats sauvegardés : {out_path}")
