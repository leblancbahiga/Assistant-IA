"""Convertir le dataset RAG évaluation en format d'entraînement LoRA MLX.

Lit tests/rag_eval_dataset.yaml, génère des fichiers train.jsonl / valid.jsonl
formatés pour le chat template Qwen2.5 Instruct.
"""

import json
import yaml
from pathlib import Path

DATA_DIR = Path("data/adapters/rag")
DATA_DIR.mkdir(parents=True, exist_ok=True)

Q_CHAT_TEMPLATE = """<|im_start|>system
Tu es NURU, assistant IA spécialisé en agronomie et chaînes de valeur agricoles.
Tu réponds UNIQUEMENT à partir des documents fournis.
Tu cites tes sources avec [Source: fichier].
Si l'information n'est pas dans les documents, tu dis que tu ne trouves pas.
<|im_end|>
<|im_start|>user
{question}
<|im_end|>
<|im_start|>assistant
{réponse}
<|im_end|>"""


def load_questions(path: str) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def build_training_example(q: dict) -> str:
    """Construit un exemple d'entraînement complet."""
    question = q["question"]
    keywords = ", ".join(q.get("expected_keywords", []))
    source = q.get("expected_source", "")
    doc_type = q.get("doc_type", "?")
    réponse = (
        f"[Source: {source}] "
        f"Type: {doc_type}. "
        f"Réponse basée sur les documents: {keywords}"
    )
    return Q_CHAT_TEMPLATE.format(question=question, réponse=réponse)


def main():
    questions = load_questions("tests/rag_eval_dataset.yaml")
    print(f"📊 {len(questions)} questions chargées")

    # Split train/valid (90/10)
    n_valid = max(1, len(questions) // 10)
    valid_set, train_set = questions[:n_valid], questions[n_valid:]

    def write_jsonl(path: str, data: list[dict]):
        with open(path, "w") as f:
            for q in data:
                f.write(json.dumps({"text": build_training_example(q)}, ensure_ascii=False) + "\n")

    train_path = str(DATA_DIR / "train.jsonl")
    valid_path = str(DATA_DIR / "valid.jsonl")

    write_jsonl(train_path, train_set)
    write_jsonl(valid_path, valid_set)

    print(f"✅ Train: {len(train_set)} → train.jsonl")
    print(f"✅ Valid: {len(valid_set)} → valid.jsonl")
    print(f"📁 Dossier: {DATA_DIR.resolve()}")


if __name__ == "__main__":
    main()
