"""Benchmark latence (p50/p95/p99) + précision — Router V16.

Usage :
    cd /path/to/assistant_ia
    python -m src.routing.v16.benchmark
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.routing.v16.router_v16 import RouterV16

LABELED_SET = [
    ("Bonjour !", "SIMPLE"),
    ("Merci beaucoup", "SIMPLE"),
    ("Qui es-tu ?", "SIMPLE"),
    ("Qui suis-je ?", "RAG"),
    ("Qui est Leblanc ?", "RAG"),
    ("Que fait actuellement la FAO ?", "WEB"),
    ("Parle-moi de mon expérience à la FAO", "RAG"),
    ("Explique la photosynthèse", "GENERAL"),
    ("Explique la photosynthèse dans mon rapport", "RAG"),
    ("Quelle est la météo aujourd'hui ?", "WEB"),
    ("Quel est le prix du riz aujourd'hui ?", "WEB"),
    ("Qui est l'actuel président des États-Unis ?", "WEB"),
    ("Combien font 12 fois 7 ?", "GENERAL"),
    ("Résume mon CV", "RAG"),
    ("Ouvre le document du projet Walikale", "RAG"),
    ("Quelle est la définition de la gravité ?", "GENERAL"),
    ("Quelles sont les dernières actualités agricoles ?", "WEB"),
    ("Cherche dans mes fichiers le rapport IITA", "RAG"),
    ("Quel est le taux d'inflation actuel ?", "WEB"),
    ("Pourquoi le ciel est bleu ?", "GENERAL"),
    ("Ma lettre de motivation pour YARID", "RAG"),
    ("Quelle est la capitale du Rwanda ?", "GENERAL"),
    ("Quel est le cours du dollar aujourd'hui ?", "WEB"),
    ("Explique-moi comment fonctionne un moteur diesel", "GENERAL"),
    ("Mon diplôme est-il dans le dossier ?", "RAG"),
    ("Qui dirige actuellement la Banque Mondiale ?", "WEB"),
    ("Résous 45 / 9", "GENERAL"),
    ("Ouvre ma présentation IITA", "RAG"),
    ("Quelles sont les nouvelles du jour ?", "WEB"),
    ("Compare mon CV avec cette offre d'emploi", "MULTI_ROUTE"),
    ("D'accord, merci", "SIMPLE"),
    ("Quel est le résultat de 8 fois 8 ?", "GENERAL"),
    ("Parle-moi de mes infos personnelles", "RAG"),
    ("Quelle est la température actuelle à Kampala ?", "WEB"),
    ("Ouvre mon rapport annuel", "RAG"),
    ("Résume-le.", "RAG"),
    ("Explique la relativité", "GENERAL"),
    ("Quel est le compte-rendu de la dernière réunion YARID ?", "RAG"),
    ("Quelles sont les actualités économiques récentes ?", "WEB"),
    ("Bonsoir", "SIMPLE"),
]


def run_precision(router):
    correct = 0
    errors = []
    for query, expected in LABELED_SET:
        d = router.route(query)
        if d.intent == expected:
            correct += 1
        else:
            errors.append((query, expected, d.intent, d.reasoning))
    return correct / len(LABELED_SET), errors


def run_latency(router, n=2000):
    queries = [q for q, _ in LABELED_SET]
    times = []
    for i in range(n):
        q = queries[i % len(queries)] + (" " if i % 7 == 0 else "")
        t0 = time.perf_counter()
        router.route(q)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return {
        "p50_ms": times[int(0.50 * n)],
        "p95_ms": times[int(0.95 * n)],
        "p99_ms": times[int(0.99 * n)],
        "max_ms": times[-1],
    }


if __name__ == "__main__":
    router = RouterV16()
    accuracy, errors = run_precision(router)
    print(f"Précision : {accuracy * 100:.1f}% ({len(LABELED_SET) - len(errors)}/{len(LABELED_SET)})")
    if errors:
        print("\nErreurs :")
        for q, expected, got, reasoning in errors:
            print(f"  [{expected} attendu, {got} obtenu] {q!r}  ({reasoning})")

    latency = run_latency(RouterV16())
    print("\nLatence (2000 requêtes, cache mixte) :")
    for k, v in latency.items():
        print(f"  {k}: {v:.4f} ms")
