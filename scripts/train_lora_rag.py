"""Entraînement LoRA pour l'adaptateur RAG NURU V15.

Usage:
    python scripts/train_lora_rag.py
    python scripts/train_lora_rag.py --iters 100 --learning-rate 5e-5
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mlx_lm import load
from mlx_lm.lora import train_model, load_dataset, build_parser


def main():
    parser = build_parser()
    parser.set_defaults(
        model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
        data="data/adapters/rag",
        adapter_path="models/adapters/rag",
        iters=200,
        batch_size=2,
        learning_rate=1e-4,
        steps_per_eval=20,
        save_every=50,
        max_seq_length=2048,
        num_layers=16,
        val_batches=-1,
        fine_tune_type="lora",
        lora_parameters={"rank": 8, "scale": 16.0},
    )
    args, _ = parser.parse_known_args()

    adapter_dir = Path(args.adapter_path)
    adapter_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Modèle: {args.model}")
    print(f"📊 Data:    {args.data}")
    print(f"💾 Adapter: {adapter_dir.resolve()}")

    # 1. Charger le modèle
    print("⏳ Chargement du modèle...")
    model, tokenizer = load(args.model)
    print("✅ Modèle chargé")

    # 2. Charger le dataset
    print("⏳ Chargement du dataset...")
    train_set, valid_set, _ = load_dataset(args, tokenizer)
    print(f"✅ Train: {len(train_set)} | Valid: {len(valid_set)}")

    # 3. Entraînement LoRA
    print(f"🚀 Lancement LoRA ({args.iters} iters)...")
    train_model(args, model, train_set, valid_set)
    print(f"✅ Adaptateur sauvegardé dans {adapter_dir.resolve()}/")


if __name__ == "__main__":
    main()
