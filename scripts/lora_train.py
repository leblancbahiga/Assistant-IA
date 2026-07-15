"""LoRA training pour NURU — version optimisée M1 8 Go.

Hyperparamètres définitifs (synthèse 3 experts + warmup + dropout) :
  - iters=400 (5 epochs sur 84 exemples)
  - max_seq_length=1024 (pas de troncature RAG)
  - num_layers=8 (pénétration comportementale)
  - lr=5e-5 + cosine decay + warmup 30 iters (apprentissage stable)
  - lora_parameters={rank=8, alpha=16, dropout=0.05, scale=16.0}
"""
import os, sys, time, logging
from types import SimpleNamespace

# ── Fix sys.path : projet avant Hermes agent ──
project_sp = "/Users/leblancbahiga/Downloads/Assistant IA/.venv/lib/python3.13/site-packages"
hermes_sp  = "/Users/leblancbahiga/.hermes/hermes-agent/venv/lib/python3.11/site-packages"
if hermes_sp in sys.path:
    sys.path.remove(hermes_sp)
if project_sp in sys.path and sys.path.index(project_sp) > 1:
    sys.path.remove(project_sp)
    sys.path.insert(1, project_sp)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lora_train")

def main():
    t_start = time.time()
    logger.info("🚀 Démarrage LoRA training — Phi-4-mini × 84 exemples RAG optimisé")

    from mlx_lm.lora import CONFIG_DEFAULTS, run

    # Synthèse des 3 propositions expert + warmup + dropout
    overrides = dict(
        model="mlx-community/Phi-4-mini-instruct-4bit",
        data="data/adapters/rag",
        adapter_path="data/adapters/rag",
        train=True,
        fine_tune_type="lora",

        # Hyperparamètres d'apprentissage
        batch_size=1,            # Intouchable sur M1 8 Go
        iters=400,               # 5 epochs (84 ex × 5 = 420, arrondi)
        learning_rate=5e-5,      # LR effectif = 1e-4 après scale×alpha/r

        # Architecture LoRA
        num_layers=8,            # Pénètre la logique du modèle sans OOM
        lora_parameters={
            "rank": 8,
            "alpha": 16.0,
            "dropout": 0.05,     # Régularisation sur petit dataset
            "scale": 16.0,
        },

        # Contexte RAG
        max_seq_length=1024,     # Pas de troncature des chunks

        # LR scheduler : warmup 30 iters + cosine decay
        lr_schedule={
            "name": "cosine_decay",
            "arguments": [5e-5, 400],
            "warmup": 30,
            "warmup_init": 0.0,
        },

        # Monitoring
        steps_per_report=20,
        steps_per_eval=50,
        val_batches=2,
        save_every=100,
        seed=42,
    )
    args = SimpleNamespace(**{**CONFIG_DEFAULTS, **overrides})

    logger.info(f"📦 Modèle: {args.model}")
    logger.info(f"📚 Données: {args.data} ({args.iters} iters, "
                f"rank={args.lora_parameters['rank']}, "
                f"seq_len={args.max_seq_length}, "
                f"lr={args.learning_rate}, "
                f"dropout={args.lora_parameters['dropout']})")
    if args.lr_schedule:
        logger.info(f"📈 Schedule: {args.lr_schedule['name']} "
                    f"with {args.lr_schedule.get('warmup', 0)} warmup steps")

    os.environ["TOKENIZERS_PARALLELISM"] = "true"
    run(args)

    dt = time.time() - t_start
    logger.info(f"✅ Training terminé en {dt:.0f}s ({dt/60:.1f} min)")

if __name__ == "__main__":
    main()
