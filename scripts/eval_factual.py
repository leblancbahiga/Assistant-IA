#!/usr/bin/env python3
"""Évaluation factuelle de l'adapter LoRA RAG.

Extrait de vrais faits du RAG index, pose des questions réelles,
vérifie que le modèle répond correctement avec [Source: ...].
"""
import sqlite3, json, os, sys, re, time, textwrap

# ── Contexte ──
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT, "indexes", "nuru.db")
ADAPTER_PATH = os.path.join(PROJECT, "data", "adapters", "rag")
MODEL = "mlx-community/Phi-4-mini-instruct-4bit"
MAX_CHECKPOINT = None  # auto : dernier checkpoint disponible
TOP_K = 5              # chunks par question

# ── Extraction des faits réels depuis le RAG ──
def extract_real_facts(db_path: str, max_facts: int = 20):
    """Extrait des chunks réels avec leur source depuis l'index RAG."""
    if not os.path.exists(db_path):
        print(f"❌ Base RAG introuvable : {db_path}")
        return []
        
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    
    # Vérifier la structure
    cur.execute("SELECT sql FROM sqlite_master WHERE name='chunks_fts'")
    print(f"[INFO] Structure FTS : {cur.fetchone()[0][:80]}...")
    
    # Extraire des chunks représentatifs
    cur.execute("""
        SELECT source, content FROM chunks_fts 
        WHERE length(content) > 100 AND length(content) < 800
        ORDER BY rowid
    """)
    
    rows = cur.fetchall()
    db.close()
    
    if not rows:
        print("❌ Aucun chunk trouvé")
        return []
    
    print(f"[INFO] {len(rows)} chunks disponibles dans l'index")
    
    # Sélectionner des chunks variés (un par source, max_facts)
    seen_sources = set()
    facts = []
    for source, content in rows:
        src_short = source.split("/")[-1] if "/" in source else source
        if src_short not in seen_sources and len(facts) < max_facts:
            seen_sources.add(src_short)
            facts.append({"source": source, "content": content.strip()})
    
    return facts


def build_dataset(db_path: str):
    """Construit un dataset d'évaluation : positifs + pièges."""
    facts = extract_real_facts(db_path, max_facts=24)
    
    dataset = []
    
    # ── Cas positifs : la réponse est dans le chunk ──
    for fact in facts:
        content = fact["content"]
        source = fact["source"]
        src_short = source.split("/")[-1]
        
        # Détecter le type de contenu pour formuler une question
        content_lower = content.lower()
        
        if len(content) < 60:
            continue  # trop court pour être significatif
        
        question = formulate_question(content, src_short)
        if question:
            dataset.append({
                "type": "positif",
                "question": question,
                "contexte": content,
                "source": source,
                "source_short": src_short,
            })
    
    # ── Cas piège : question sur un sujet NON présent ──
    trap_questions = [
        "Quel est le chiffre d'affaires de BEACCOM en 2025 ?",
        "Donne-moi le numéro de téléphone de Leblanc Bahiga.",
        "Quelle est la date de naissance de Toussaint Omombo ?",
        "Combien de personnes vivent dans le village de Beyogoya ?",
        "Quel est le salaire mensuel du moniteur de terrain ?",
    ]
    for q in trap_questions:
        # Contexte = extrait RAG qui ne contient PAS la réponse
        random_fact = facts[len(dataset) % len(facts)] if facts else facts
        dataset.append({
            "type": "piège",
            "question": q,
            "contexte": random_fact["content"] if random_fact else "Contexte non disponible.",
            "source": random_fact["source"] if random_fact else "inconnu",
            "source_short": random_fact["source"].split("/")[-1] if random_fact else "inconnu",
        })
    
    return dataset


def formulate_question(content: str, source: str) -> str:
    """Génère une question factuelle à partir du contenu du chunk."""
    content_lower = content.lower()
    
    # Règle 1 : Si le chunk commence par un nom / titre
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    first_line = lines[0] if lines else ""
    
    # Règle 2 : Contient des mots-clés numériques
    if re.search(r'\d+', content) and len(content) < 300:
        # Contient des nombres → demander une valeur chiffrée
        prefix = content[:min(80, len(content)//2)].strip()
        if len(prefix) > 20:
            return f"D'après le document '{source}', quelle information chiffrée est mentionnée dans ce passage : « {prefix}… » ?"
    
    # Règle 3 : Contient un nom propre
    names = re.findall(r'[A-Z][a-zéèêëàâîïôùûç]{2,}(?:\s[A-Z][a-zéèêëàâîïôùûç]{2,}){1,2}', content[:200])
    if names:
        return f"Que dit le document '{source}' à propos de {names[0]} ?"
    
    # Règle 4 : Question générique sur le sujet du chunk
    words = content.split()
    subject_words = [w for w in words[:15] if len(w) > 5 and w[0].isupper()]
    if subject_words:
        subject = subject_words[0]
        return f"D'après '{source}', qu'est-ce qui est dit à propos de {subject} ?"
    
    # Fallback
    return f"Résume le passage suivant du document '{source}' : « {content[:80]}… »"


def get_latest_checkpoint(adapter_path: str) -> str:
    """Trouve le checkpoint le plus récent."""
    import glob
    ckpts = glob.glob(os.path.join(adapter_path, "*_adapters.safetensors"))
    # Exclure le fichier principal (adapters.safetensors = dernier it)
    ckpts = [c for c in ckpts if not os.path.basename(c) == "adapters.safetensors"]
    if not ckpts:
        # Fallback : adapter principal
        main = os.path.join(adapter_path, "adapters.safetensors")
        if os.path.exists(main):
            return main
        return None
    
    def parse_iter(p):
        m = re.search(r'(\d+)_adapters', os.path.basename(p))
        return int(m.group(1)) if m else 0
    
    ckpts.sort(key=parse_iter)
    return ckpts[-1]


def print_progress(current, total, bar_length=40):
    """Affiche une barre de progression."""
    filled = int(bar_length * current // total)
    bar = '█' * filled + '░' * (bar_length - filled)
    pct = current / total * 100
    print(f"\r  [{bar}] {pct:.0f}% ({current}/{total})", end="", flush=True)
    if current == total:
        print()


def evaluate(dataset, adapter_checkpoint):
    """Évalue l'adapter sur le dataset factuel."""
    print(f"\n{'='*60}")
    print(f"🔍 ÉVALUATION ADAPTER LORA RAG")
    print(f"📦 Modèle : {MODEL}")
    print(f"🎯 Adapter : {adapter_checkpoint}")
    print(f"📊 Dataset : {len(dataset)} questions ({sum(1 for d in dataset if d['type']=='positif')} positifs, {sum(1 for d in dataset if d['type']=='piège')} pièges)")
    print(f"{'='*60}\n")
    
    # Charger modèle + adapter (MLX)
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
    
    # adapter_path doit être un dossier contenant adapters.safetensors + adapter_config.json
    # Utiliser le dossier parent + copier le checkpoint si nécessaire
    adapter_dir = os.path.dirname(adapter_checkpoint) if os.path.isfile(adapter_checkpoint) else adapter_checkpoint
    
    try:
        model, tokenizer = load(
            MODEL,
            adapter_path=adapter_dir,
        )
    except Exception as e:
        print(f"❌ Erreur chargement modèle : {e}")
        return
    
    results = []
    
    print(f"\n📝 Exécution des {len(dataset)} questions...\n")
    
    for i, item in enumerate(dataset):
        print(f"\n─── Question {i+1}/{len(dataset)} : [{item['type'].upper()}] ───")
        print(f"📄 Source : {item['source_short']}")
        print(f"❓ {item['question']}")
        
        # Construire le prompt ChatML avec contexte RAG
        system_prompt = f"""Tu es NURU, assistant cognitif local. Tu réponds UNIQUEMENT à partir des documents fournis dans le contexte. Cite tes sources avec [Source: nom]. Si la réponse ne se trouve pas dans le contexte, dis-le clairement.

CONTEXTE DOCUMENTAIRE LOCAL TROUVÉ :
[{item['source_short']}]
{item['contexte']}

INSTRUCTION : Réponds UNIQUEMENT à partir du contexte ci-dessus."""
        
        prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{item['question']}<|im_end|>\n<|im_start|>assistant\n"
        
        # Générer
        try:
            response = generate(
                model, tokenizer,
                prompt=prompt,
                max_tokens=200,
                sampler=make_sampler(0.1),
                verbose=False,
            )
            response = response.strip()
        except Exception as e:
            response = f"[ERREUR] {e}"
        
        # Analyse de la réponse
        has_source = bool(re.search(r'\[Source:', response))
        is_refusal = any(p in response.lower() for p in [
            "je ne trouve pas", "ne se trouve pas", "pas dans le contexte",
            "ne peux pas répondre", "information non disponible"
        ])
        
        # Score
        if item["type"] == "positif":
            if has_source and not is_refusal:
                score = "✅ BON"
                correct_sources = 1 if has_source else 0
            elif has_source and is_refusal:
                score = "⚠️ SOURCE MAIS REFUS"
                correct_sources = 1
            elif not has_source and not is_refusal:
                score = "❌ PAS DE SOURCE"
                correct_sources = 0
            else:
                score = "❌ REFUS INCORRECT"
                correct_sources = 0
        else:  # piège
            if is_refusal:
                score = "✅ BON (refus correct)"
                correct_sources = 1
            elif has_source and not is_refusal:
                score = "❌ HALLUCINATION (aurait dû refuser)"
                correct_sources = 0
            else:
                score = "⚠️ RÉPONSE SANS SOURCE"
                correct_sources = 0
        
        # Tronquer pour affichage
        resp_short = textwrap.shorten(response, width=200, placeholder="...")
        print(f"💬 {resp_short}")
        print(f"🎯 {score}")
        
        results.append({
            "question": item["question"],
            "type": item["type"],
            "source_attendue": item["source_short"],
            "reponse": response,
            "a_source": has_source,
            "a_refuse": is_refusal,
            "score": score,
        })
        
        print_progress(i+1, len(dataset))
    
    # ── Synthèse ──
    print(f"\n\n{'='*60}")
    print("📊 SYNTHÈSE DE L'ÉVALUATION")
    print(f"{'='*60}")
    
    positifs = [r for r in results if r["type"] == "positif"]
    pieges = [r for r in results if r["type"] == "piège"]
    
    if positifs:
        bons_positifs = sum(1 for r in positifs if r["score"].startswith("✅"))
        print(f"\n📈 Questions POSITIVES : {bons_positifs}/{len(positifs)} ✅ ({100*bons_positifs//len(positifs)}%)")
        for r in positifs:
            print(f"  {'✅' if r['score'].startswith('✅') else '❌'} {r['question'][:70]} → {r['score']}")
    
    if pieges:
        bons_pieges = sum(1 for r in pieges if r["score"].startswith("✅"))
        print(f"\n🪤 Questions PIÈGE : {bons_pieges}/{len(pieges)} ✅ ({100*bons_pieges//len(pieges)}%)")
        for r in pieges:
            print(f"  {'✅' if r['score'].startswith('✅') else '❌'} {r['question'][:70]} → {r['score']}")
    
    total_bon = sum(1 for r in results if r["score"].startswith("✅"))
    print(f"\n📊 SCORE GLOBAL : {total_bon}/{len(results)} ✅ ({100*total_bon//len(results)}%)")
    
    # Sauvegarder les résultats
    out_path = os.path.join(PROJECT, "data", "adapters", "rag", "eval_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "checkpoint": adapter_checkpoint,
            "total": len(results),
            "bons": total_bon,
            "pct": round(100*total_bon/len(results), 1),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Résultats sauvegardés : {out_path}")
    print(f"{'='*60}\n")


def main():
    # Construire le dataset factuel
    print("🔍 Construction du dataset d'évaluation factuelle...")
    dataset = build_dataset(DB_PATH)
    
    if not dataset:
        print("❌ Dataset vide - vérifie la base RAG")
        return
    
    print(f"✅ Dataset : {len(dataset)} questions factuelles")
    for i, item in enumerate(dataset[:3]):
        print(f"  {i+1}. [{item['type']}] {item['question'][:80]}")
    if len(dataset) > 3:
        print(f"  ... et {len(dataset)-3} autres")
    
    # Trouver le meilleur checkpoint
    ckpt = get_latest_checkpoint(ADAPTER_PATH)
    if not ckpt:
        print(f"\n⏳ Aucun checkpoint trouvé dans {ADAPTER_PATH}")
        print("   Le training n'a pas encore sauvegardé. Réessaie après iter 100.")
        # Sauvegarder le dataset pour exécution ultérieure
        out = os.path.join(PROJECT, "data", "adapters", "rag", "eval_dataset.json")
        with open(out, "w") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
        print(f"   Dataset sauvegardé dans {out} pour lancement manuel.")
        print(f"   Pour exécuter : python3 scripts/eval_lora_adapter.py")
        return
    
    print(f"\n📦 Checkpoint : {ckpt}")
    
    # Lancer l'évaluation
    evaluate(dataset, ckpt)


if __name__ == "__main__":
    main()
