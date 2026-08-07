"""Tests pour scripts/eval_lora_adapter.py — validation du formatage et de la
structure des questions, SANS charger MLX (evite conflit GPU avec le training)."""

import importlib.util
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "eval_lora_adapter", PROJECT_ROOT / "scripts" / "eval_lora_adapter.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_module()


class TestEvalLoRAAdapter:
    def test_base_model_is_phi4(self, mod):
        """Le modele de base doit etre Phi-4-mini (matche l'adapter, pas Qwen)."""
        assert "Phi-4-mini" in mod.BASE_MODEL

    def test_prompt_format_matches_training(self, mod):
        """Le prompt doit etre en ChatML identique au dataset d'entrainement."""
        ex = mod.QUESTIONS[0]
        p = mod.build_prompt(ex)
        assert p.startswith("<|im_start|>system")
        assert "<|im_start|>user" in p
        assert "<|im_start|>assistant" in p
        # le contexte RAG et la question y figurent
        assert ex["context"] in p
        assert ex["question"] in p

    def test_six_questions_5rag_1piege(self, mod):
        rag = [q for q in mod.QUESTIONS if q["type"] == "RAG"]
        piege = [q for q in mod.QUESTIONS if q["type"] == "PIEGE"]
        assert len(mod.QUESTIONS) == 6
        assert len(rag) == 5
        assert len(piege) == 1
        # le piege doit avoir attendu_source = None (on attend un refus)
        assert piege[0]["attendu_source"] is None

    def test_adapter_checkpoints_present(self, mod):
        """L'adapter final et le checkpoint 300 doivent exister sur disque."""
        assert os.path.exists(PROJECT_ROOT / "data" / "adapters" / "rag")
        assert os.path.exists(
            PROJECT_ROOT / "data" / "adapters" / "rag" / "0000300_adapters.safetensors"
        )

    def test_piege_question_absent_du_contexte(self, mod):
        """La question piege ne doit pas etre repondable par le contexte fourni."""
        piege = next(q for q in mod.QUESTIONS if q["type"] == "PIEGE")
        assert "kinshasa" in piege["question"].lower()
        assert "kinshasa" not in piege["context"].lower()
