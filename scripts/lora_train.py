"""LoRA training pour NURU — version allégée M1 8 Go."""

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
    logger.info("🚀 Démarrage LoRA training — Phi-4-mini × 84 exemples RAG")

    from mlx_lm.lora import CONFIG_DEFAULTS, run

    # Merge : mes surcharges par-dessus CONFIG_DEFAULTS
    overrides = dict(
        model="mlx-community/Phi-4-mini-instruct-4bit",
        data="data/adapters/rag",
        adapter_path="data/adapters/rag",
        train=True,
        fine_tune_type="lora",
        num_layers=4,
        batch_size=1,
        iters=100,
        learning_rate=5e-5,
        steps_per_report=10,
        steps_per_eval=20,
        val_batches=2,
        max_seq_length=512,
        save_every=50,
        seed=42,
    )
    args = SimpleNamespace(**{**CONFIG_DEFAULTS, **overrides})

    logger.info(f"📦 Modèle: {args.model}")
    logger.info(f"📚 Données: {args.data} ({args.iters} iters, rank={args.lora_parameters['rank']})")

    os.environ["TOKENIZERS_PARALLELISM"] = "true"
    run(args)

    dt = time.time() - t_start
    logger.info(f"✅ Training terminé en {dt:.0f}s ({dt/60:.1f} min)")

if __name__ == "__main__":
    main()
