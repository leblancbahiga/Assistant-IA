"""Évaluation de l'adaptateur LoRA RAG NURU — comparaison BASE vs ADAPTER.

Charge Phi-4-mini (modele de base de l'adapter) via mlx_lm direct,
en bypassant LocalLLM (dont la config pointe sur Qwen 1.5B -> incompatible).

Pour chaque question RAG réelle + 1 piège, on génère:
  - BASE       : Phi-4-mini sans adapter
  - ADAPTER    : checkpoint final 2000 iters
  - ADAPTER@300: checkpoint 300 iters (meilleure val loss connue)

Usage:
    cd /path/projet && PYTHONPATH="" .venv/bin/python scripts/eval_lora_adapter.py
    PYTHONPATH="" .venv/bin/python scripts/eval_lora_adapter.py --adapter data/adapters/rag
"""
import argparse
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Fix sys.path : projet avant Hermes agent ──
project_sp = str(PROJECT_ROOT / ".venv" / "lib" / "python3.13" / "site-packages")
hermes_sp = "/Users/leblancbahiga/.hermes/hermes-agent/venv/lib/python3.11/site-packages"
if hermes_sp in sys.path:
    sys.path.remove(hermes_sp)
if project_sp in sys.path and sys.path.index(project_sp) > 1:
    sys.path.remove(project_sp)
    sys.path.insert(1, project_sp)

from mlx_lm import load
from mlx_lm.utils import load_adapters
from mlx_lm import generate
from mlx_lm.sample_utils import make_sampler, make_repetition_penalty

BASE_MODEL = "mlx-community/Phi-4-mini-instruct-4bit"

SYSTEM_PROMPT = (
    "Tu es NURU, assistant IA spécialisé en agronomie et chaînes de valeur agricoles.\n"
    "Tu réponds UNIQUEMENT à partir des documents fournis ci-dessous.\n"
    "Tu cites tes sources avec [Source: nom_fichier].\n"
    "Si l'information n'est pas dans les documents, tu dis que tu ne trouves pas.\n"
    "Tu es concis et tu vas droit au but."
)

QUESTIONS = [
    # 5 questions RAG ancrées sur des faits REELS de nuru.db (BEACCOM / PASA-NK / Nord Kivu)
    {
        "type": "RAG",
        "context": (
            "[Document 1] Proposition Technique BEACCOM 2025 : Étude d'analyse de la "
            "vulnérabilité des moyens d'existence aux changements climatiques dans le "
            "Nord Kivu, dans la zone d'intervention du projet PASA-NK. "
            "[Document 2] Le bureau de BEACCOM est situé à Goma, avec des réunions de "
            "cadrage avec l'équipe du PASA-NK."
        ),
        "question": "Quel est l'objet de l'étude BEACCOM 2025 et dans quelle province se déroule-t-elle ?",
        "attendu_source": "BEACCOM",
    },
    {
        "type": "RAG",
        "context": (
            "[Document 1] L'étude BEACCOM analyse la vulnérabilité des moyens d'existence "
            "aux changements climatiques dans la zone d'intervention du projet PASA-NK "
            "au Nord Kivu. [Document 2] Les déplacements sur le terrain se font en 4x4 "
            "avec chauffeur, en tenant compte des conditions d'accès difficiles et des "
            "contraintes sécuritaires."
        ),
        "question": "Quel projet est cité comme zone d'intervention de l'étude BEACCOM ?",
        "attendu_source": "PASA-NK",
    },
    {
        "type": "RAG",
        "context": (
            "[Document 1] ETUDE DE MARCHE | KoboToolbox : rapport automatisé basé sur "
            "50 submissions de données brutes. [Document 2] La concentration des achats "
            "au Port de Kalemie suggère un rôle central : le haricot vendu à Kalemie "
            "provient principalement de Moba, Goma ou la Tanzanie."
        ),
        "question": "Combien de soumissions compte le rapport KoboToolbox de l'étude de marché, et d'où provient le haricot vendu à Kalemie ?",
        "attendu_source": "KoboToolbox",
    },
    {
        "type": "RAG",
        "context": (
            "[Document 1] Proposition Technique BEACCOM : la phase préparatoire dure 2 "
            "semaines, dont 1 semaine de revue documentaire et analyse contextuelle. "
            "[Document 2] Les livrables incluent le Rapport de la revue documentaire et "
            "de l'analyse contextuelle."
        ),
        "question": "Quelle est la durée de la phase préparatoire de l'étude BEACCOM et que livre-t-elle ?",
        "attendu_source": "BEACCOM",
    },
    {
        "type": "RAG",
        "context": (
            "[Document 1] ANALYSE ETUDE DE MARCHE : le haricot vendu à Kalemie n'est pas "
            "produit localement et provient de Moba, Goma ou la Tanzanie. "
            "[Document 2] La diversité des marchés de vente indique une dispersion des "
            "circuits d'approvisionnement."
        ),
        "question": "Le haricot vendu à Kalemie est-il produit localement ? D'où provient-il ?",
        "attendu_source": "Kalemie",
    },
    # 1 PIÈGE : sujet absent du corpus (vérifié : 0 occurrence de 'Kinshasa' comme antenne BEACCOM)
    {
        "type": "PIEGE",
        "context": (
            "[Document 1] Proposition Technique BEACCOM 2025 : étude de vulnérabilité "
            "dans le Nord Kivu, bureau à Goma, dans la zone d'intervention du projet "
            "PASA-NK. [Document 2] Déplacements terrain en 4x4 avec chauffeur."
        ),
        "question": "Quelle est l'adresse et le numéro de téléphone de l'antenne BEACCOM à Kinshasa ?",
        "attendu_source": None,  # absence documentaire -> on attend un REFUS
    },
]


def build_prompt(example: dict) -> str:
    user_msg = f"{example['context']}\n\nQuestion : {example['question']}"
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{user_msg}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def generate_for(model, tokenizer, prompt: str) -> str:
    # Même API que LocalLLM.generate : sampler via make_sampler + rep penalty
    sampler = make_sampler(temp=0.1, top_p=0.9, min_p=0.1)
    logits_processors = [make_repetition_penalty(1.05)]
    return generate(
        model, tokenizer, prompt,
        sampler=sampler, logits_processors=logits_processors, max_tokens=256,
    )


def load_model_with(adapter_path: str | None, adapter_config_dir: str | None = None):
    # load() exige un DOSSIER (adapter_config.json). Un checkpoint isolé
    # (.safetensors) nécessite un dossier temp avec config + poids renomme.
    if adapter_path and adapter_path.endswith(".safetensors"):
        model, tokenizer = load(BASE_MODEL)
        # Créer un dossier temp avec adapter_config.json + adapters.safetensors
        config_dir = adapter_config_dir or "data/adapters/rag"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy(adapter_path, tmp_path / "adapters.safetensors")
            shutil.copy(Path(config_dir) / "adapter_config.json",
                       tmp_path / "adapter_config.json")
            model = load_adapters(model, str(tmp_path))
    elif adapter_path:
        model, tokenizer = load(BASE_MODEL, adapter_path=adapter_path)
    else:
        model, tokenizer = load(BASE_MODEL)
    return model, tokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="data/adapters/rag",
                   help="Dossier de l'adapter final (2000 iters)")
    ap.add_argument("--ckpt300", default="data/adapters/rag/0000300_adapters.safetensors",
                   help="Checkpoint 300 iters (meilleure val connue)")
    args = ap.parse_args()

    adapter_dir = Path(args.adapter)
    ckpt300 = Path(args.ckpt300)

    print(f"🔧 Modèle de base: {BASE_MODEL}")
    print(f"📦 Adapter final: {adapter_dir.resolve() if adapter_dir.exists() else 'ABSENT'}")
    print(f"📦 Checkpoint 300: {ckpt300.resolve() if ckpt300.exists() else 'ABSENT'}")
    print("=" * 70)

    results = {"base": [], "adapter": [], "adapter300": []}

    # 1. BASE (sans adapter)
    print("\n🟦 CHARGEMENT BASE (sans adapter)...")
    t0 = time.time()
    model_b, tok_b = load_model_with(None)
    print(f"   Base chargée en {time.time()-t0:.1f}s")
    for i, ex in enumerate(QUESTIONS):
        p = build_prompt(ex)
        out = generate_for(model_b, tok_b, p)
        results["base"].append(out.strip())
        print(f"\n--- BASE Q{i+1} [{ex['type']}] ---")
        print(out.strip()[:400])

    # 2. ADAPTER final
    if adapter_dir.exists():
        print("\n\n🟩 CHARGEMENT ADAPTER (final 2000 iters)...")
        t0 = time.time()
        model_a, tok_a = load_model_with(str(adapter_dir))
        print(f"   Adapter chargé en {time.time()-t0:.1f}s")
        for i, ex in enumerate(QUESTIONS):
            p = build_prompt(ex)
            out = generate_for(model_a, tok_a, p)
            results["adapter"].append(out.strip())
            print(f"\n--- ADAPTER Q{i+1} [{ex['type']}] ---")
            print(out.strip()[:400])

    # 3. ADAPTER@300 (checkpoint)
    if ckpt300.exists():
        print("\n\n🟨 CHARGEMENT ADAPTER@300 (checkpoint 300 iters)...")
        t0 = time.time()
        model_c, tok_c = load_model_with(str(ckpt300), str(adapter_dir))
        print(f"   Checkpoint 300 chargé en {time.time()-t0:.1f}s")
        for i, ex in enumerate(QUESTIONS):
            p = build_prompt(ex)
            out = generate_for(model_c, tok_c, p)
            results["adapter300"].append(out.strip())
            print(f"\n--- ADAPTER@300 Q{i+1} [{ex['type']}] ---")
            print(out.strip()[:400])

    # 4. Analyse comportementale
    print("\n" + "=" * 70)
    print("📊 ANALYSE COMPORTEMENTALE")
    print("=" * 70)

    def score_source_rag(outs):
        ok = 0
        for ex, o in zip(QUESTIONS, outs):
            if ex["type"] != "RAG":
                continue
            if ex["attendu_source"] and ex["attendu_source"].lower() in o.lower():
                ok += 1
        n_rag = sum(1 for e in QUESTIONS if e["type"] == "RAG")
        return ok, n_rag

    def score_piege(outs):
        piege_idx = [i for i, e in enumerate(QUESTIONS) if e["type"] == "PIEGE"]
        ok = 0
        for i in piege_idx:
            o = outs[i].lower()
            if "ne trouve" in o or "n'est pas" in o or "pas dans" in o or "introuvab" in o:
                ok += 1
        return ok, len(piege_idx)

    for label, key in [("BASE", "base"), ("ADAPTER", "adapter"), ("ADAPTER@300", "adapter300")]:
        if not results[key]:
            continue
        s_ok, s_n = score_source_rag(results[key])
        p_ok, p_n = score_piege(results[key])
        print(f"\n{label}:")
        print(f"  Sources citées (RAG): {s_ok}/{s_n}")
        print(f"  Piège refusé:        {p_ok}/{p_n}")

    # Sauvegarde JSON
    out_path = PROJECT_ROOT / "data" / "adapters" / "rag" / "eval_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_model": BASE_MODEL,
        "questions": [{"type": e["type"], "question": e["question"],
                       "attendu_source": e["attendu_source"]} for e in QUESTIONS],
        "responses": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Résultats sauvés: {out_path}")


if __name__ == "__main__":
    main()
