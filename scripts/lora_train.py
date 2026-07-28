#!/usr/bin/env python3
"""Train LoRA adapter on the generated RAG Q/A dataset.

Usage: python scripts/lora_train.py
Expected runtime: ~4h on M1 8GB for 2000 iters.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace
from mlx_lm.lora import CONFIG_DEFAULTS, run

os.environ["TOKENIZERS_PARALLELISM"] = "true"

overrides = dict(
    model="mlx-community/Phi-4-mini-instruct-4bit",
    data="data/adapters/rag",
    adapter_path="data/adapters/rag",
    train=True,
    fine_tune_type="lora",
    num_layers=4,
    batch_size=1,
    iters=2000,
    learning_rate=5e-5,
    max_seq_length=1024,
    grad_checkpoint=True,
    clear_cache_threshold=1024,
    lora_parameters={
        "rank": 8,
        "alpha": 16,
        "dropout": 0.05,
        "scale": 16.0,
    },
    lr_schedule={
        "name": "cosine_decay",
        "arguments": [5e-5, 2000],
        "warmup": 30,
        "warmup_init": 0.0,
    },
    save_every=100,
    steps_per_report=20,
    steps_per_eval=50,
    val_batches=2,
    seed=42,
)

args = SimpleNamespace(**{**CONFIG_DEFAULTS, **overrides})
print(f"🚀 Training LoRA: {args.model}")
print(f"   Data: {args.data} ({sum(1 for _ in open(f'{args.data}/train.jsonl'))} train, "
      f"{sum(1 for _ in open(f'{args.data}/valid.jsonl'))} valid)")
print(f"   Params: layers={args.num_layers}, seq={args.max_seq_length}, "
      f"rank={args.lora_parameters['rank']}, iters={args.iters}")
print(f"   RAM: grad_checkpoint={args.grad_checkpoint}, "
      f"clear_cache={args.clear_cache_threshold}")
print()

run(args)
