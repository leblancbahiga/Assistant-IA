"""Tests V18-15 — juge niveau 1 (CitationJudge) + taxonomie hallucinations.

Cible : `src/benchmark/judge.py`.

Vérifie :
- CitationJudge.coverage : citation valide / invalide / absente / partielle ;
- CitationJudge.annotated_affirmations : découpe phrase + coverage par phrase ;
- HallucinationTaxonomy.classify : labels A/B/C/D sur cas synthétiques ;
- HallucinationTaxonomy.distribution : comptage complet A/B/C/D.

Zéro LLM, zéro modèle — juge 100 % déterministe (spec V18-15 §3.4).
"""

import pytest

from src.benchmark.judge import (
    HALLUCINATION_LABELS,
    CitationJudge,
    HallucinationTaxonomy,
    SOURCE_RE,
)


# ── CitationJudge.coverage ────────────────────────────────────────

def test_coverage_valid_citation():
    """Citation présente dans le contexte → coverage 1.0."""
    judge = CitationJudge()
    response = "Le Bénin produit du coton [SOURCE 1]."
    context = "Chunk 1: agriculture béninoise [SOURCE 1]"
    assert judge.coverage(response, context) == 1.0


def test_coverage_invalid_citation():
    """Citation hors contexte → coverage 0.0 (jamais inventée)."""
    judge = CitationJudge()
    response = "Le riz est cultivé [SOURCE 3]."
    context = "Chunk 1: agriculture [SOURCE 1]"
    assert judge.coverage(response, context) == 0.0


def test_coverage_no_citation():
    """Aucune citation dans la réponse → coverage 0.0."""
    judge = CitationJudge()
    assert judge.coverage("Réponse sans aucune référence.", "Contexte [SOURCE 1]") == 0.0


def test_coverage_partial():
    """2 citations, 1 disponible → 0.5."""
    judge = CitationJudge()
    response = "A [SOURCE 1] et B [SOURCE 4]."
    context = "[SOURCE 1] contenu"
    assert judge.coverage(response, context) == 0.5


def test_coverage_empty_context():
    """Contexte vide → aucune source disponible → 0.0."""
    judge = CitationJudge()
    assert judge.coverage("Texte [SOURCE 1]", "") == 0.0


def test_coverage_duplicate_citations_counted_once_per_occurrence():
    """Chaque occurrence citée compte ; une citation répétée valide reste 1.0."""
    judge = CitationJudge()
    response = "[SOURCE 1] puis [SOURCE 1]."
    context = "[SOURCE 1] ok"
    assert judge.coverage(response, context) == 1.0


def test_source_re_matches_format():
    """Le regex accepte le format réel [SOURCE i] (rag_engine.py:1274)."""
    assert SOURCE_RE.findall("[SOURCE 12] texte") == ["12"]
    assert SOURCE_RE.findall("pas de source") == []


# ── CitationJudge.annotated_affirmations ──────────────────────────

def test_annotated_affirmations_splits_sentences():
    judge = CitationJudge()
    resp = "Première phrase [SOURCE 1]. Deuxième phrase."
    out = judge.annotated_affirmations(resp, "[SOURCE 1] contexte")
    assert out["n_affirmations"] == 2
    assert out["affirmations"][0]["cited"] == ["1"]
    assert out["affirmations"][1]["cited"] == []


def test_annotated_affirmations_no_citations_coverage_zero():
    judge = CitationJudge()
    out = judge.annotated_affirmations("Une seule phrase.", "[SOURCE 1]")
    assert out["n_affirmations"] == 1
    assert out["coverage"] == 0.0
    assert out["affirmations"][0]["coverage"] == 0.0


def test_annotated_affirmations_partial_phrase_coverage():
    judge = CitationJudge()
    resp = "A [SOURCE 1]. B [SOURCE 5]."
    out = judge.annotated_affirmations(resp, "[SOURCE 1] seulement")
    # Phrase 1 : 1/1 ; phrase 2 : 0/1 → moyenne 0.5
    assert out["coverage"] == 0.5


# ── HallucinationTaxonomy.classify ────────────────────────────────

def test_taxonomy_a_no_context():
    """A — contexte absent : aucune source récupérée."""
    taxo = HallucinationTaxonomy()
    assert taxo.classify("", 0.0) == "A"


def test_taxonomy_b_low_coverage():
    """B — contexte présent mais couverture faible (< 0.5)."""
    taxo = HallucinationTaxonomy()
    assert taxo.classify("[SOURCE 1] contexte", 0.2) == "B"


def test_taxonomy_c_medium_coverage():
    """C — coverage moyenne (0.5-0.95) sans invention détectée."""
    taxo = HallucinationTaxonomy()
    # coverage 0.7 ≥ 0.5 et < 0.95 → C
    assert taxo.classify("[SOURCE 1] contexte", 0.7, {"faithfulness": 0.8}) == "C"


def test_taxonomy_d_low_faithfulness():
    """D — inventé malgré bon contexte (faithfulness < 0.4)."""
    taxo = HallucinationTaxonomy()
    assert taxo.classify("[SOURCE 1] contexte", 0.9, {"faithfulness": 0.1}) == "D"


def test_taxonomy_high_coverage_without_level2_not_failure():
    """Coverage élevée sans niveau 2 → label B/C (pas d'échec inventé)."""
    taxo = HallucinationTaxonomy()
    label = taxo.classify("[SOURCE 1] contexte", 0.99)
    assert label in ("B", "C")


def test_taxonomy_labels_are_known():
    taxo = HallucinationTaxonomy()
    for cov in (0.0, 0.3, 0.6, 0.9, 1.0):
        label = taxo.classify("contexte [SOURCE 1]", cov)
        assert label in HALLUCINATION_LABELS


# ── HallucinationTaxonomy.distribution ────────────────────────────

def test_distribution_counts_all_labels():
    taxo = HallucinationTaxonomy()
    dist = taxo.distribution(["A", "B", "B", "D"])
    assert dist == {"A": 1, "B": 2, "C": 0, "D": 1}


def test_distribution_empty_returns_zeros():
    taxo = HallucinationTaxonomy()
    assert taxo.distribution([]) == {"A": 0, "B": 0, "C": 0, "D": 0}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
