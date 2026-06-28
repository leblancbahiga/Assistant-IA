#!/usr/bin/env python3
"""Seed le profil utilisateur de Leblanc dans les bases mémoire de NURU.

Correction du problème où NURU ne connaît pas son utilisateur
et hallucine des informations personnelles.

Usage: python3 scripts/seed_user_profile.py
"""
import sqlite3
import sys
import time
from pathlib import Path

# ── Profil détaillé de Leblanc BAHIGA Mudarhi ──
V9_PROFILE = {
    'identity': {
        'name': 'Leblanc BAHIGA Mudarhi',
        'title': 'Ingénieur Agronome & Informaticien — Spécialiste des chaînes de valeur agricoles',
        'age': '46 ans',
        'nationality': 'République Démocratique du Congo (RDC)',
        'residence': 'Kampala, Ouganda',
        'languages': 'Français, Anglais, Swahili',
    },
    'professional': {
        'employer': 'IITA (International Institute of Tropical Agriculture)',
        'role': 'Agriculture Value Chain Specialist — Digital ag, chaînes de valeur, advisory',
        'past_employers': 'FAO, World Bank, USAID — projets agricoles Afrique centrale et orientale',
        'education': 'MBA en cours + formation en informatique',
        'expertise': 'Agriculture digitale, chaînes de valeur, biochar, systèmes agroalimentaires',
    },
    'preference': {
        'communication_style': 'Préfère réponses précises, concises, factuelles. Pas de remplissage.',
        'ux_standard': 'Pixel-perfect, implémentations réelles, pas de descriptions',
        'work_style': 'Multi-agents, analyse critique type architecte senior',
        'language': 'Français (natif), Anglais (pro)',
        'patience': 'Frustré si >30s sans feedback — préfère un status rapide au silence',
    },
    'context': {
        'project_nuru': 'NURU — Personal Cognitive OS (système cognitif personnel)',
        'nuru_philosophy': 'Mémoire > LLM | Objectifs > Prompts | Projets > Chat | Connecteurs > Agents | UX > Benchmarks',
        'nuru_stack': 'PySide6, MLX (Phi-4-mini), SQLite, RAG hybride, Apple Silicon M1',
    },
}

# Same data for the index DB facts table
INDEX_FACTS = [
    ("identity", "Leblanc BAHIGA Mudarhi — 46 ans, Ingénieur Agronome & Informaticien"),
    ("identity", "Nationalité : RDC, Résidence : Kampala, Ouganda"),
    ("identity", "Langues : Français, Anglais, Swahili"),
    ("professional", "Employeur : IITA — Agriculture Value Chain Specialist"),
    ("professional", "Anciens employeurs : FAO, World Bank, USAID"),
    ("professional", "Expertise : Agriculture digitale, chaînes de valeur, biochar"),
    ("professional", "Formation : MBA en cours + informatique"),
    ("preferences", "Style de communication : précis, concis, factuel"),
    ("preferences", "Exige du pixel-perfect et des implémentations réelles"),
    ("preferences", "Apprécie le parallélisme multi-agents"),
    ("preferences", "Langue : Français natif, Anglais professionnel"),
    ("project", "NURU — Personal Cognitive OS (système d'exploitation cognitif personnel)"),
    ("project", "Philosophie NURU: Mémoire > LLM | Objectifs > Prompts | Projets > Chat | Connecteurs > Agents | UX > Benchmarks"),
    ("project", "Stack : PySide6, MLX (Phi-4-mini), SQLite, RAG hybride, Apple Silicon M1"),
]

INDEX_DB = "/Users/leblancbahiga/Downloads/Assistant IA/indexes/nuru.db"
V9_DB = str(Path.home() / ".nuru" / "memory_v9.db")


def seed_v9_user_memory():
    """Remplit user_memory (key-value) dans memory_v9.db — utilisée par MemoryBridge."""
    conn = sqlite3.connect(V9_DB)
    
    # Vider (safe car la table est vide actuellement)
    existing = conn.execute('SELECT COUNT(*) FROM user_memory').fetchone()[0]
    if existing > 0:
        print(f"  ℹ️  user_memory contient déjà {existing} entrées — mise à jour par REPLACE")
    
    now = time.time()
    count = 0
    for category, entries in V9_PROFILE.items():
        for key, value in entries.items():
            conn.execute(
                """INSERT OR REPLACE INTO user_memory
                   (key, value, category, confidence, updated_at, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, value, category, 0.95, now, 'seed')
            )
            count += 1
    
    conn.commit()
    print(f"✅ V9 DB: {count} entrées dans user_memory")
    
    rows = conn.execute('SELECT key, value, category FROM user_memory ORDER BY category, key').fetchall()
    for r in rows:
        print(f"   [{r[2]}] {r[0]} = {r[1][:70]}")
    conn.close()
    return count


def seed_index_facts():
    """Remplit facts dans l'index DB — utilisée par get_recent_facts()."""
    conn = sqlite3.connect(INDEX_DB)
    
    existing = conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    if existing > 0:
        print(f"  ℹ️  facts contient déjà {existing} entrées — remplacement")
        conn.execute("DELETE FROM facts")
    
    count = 0
    for category, content in INDEX_FACTS:
        conn.execute(
            "INSERT INTO facts (content, category) VALUES (?, ?)",
            (content, category)
        )
        count += 1
    
    conn.commit()
    print(f"✅ Index DB: {count} faits dans facts")
    
    rows = conn.execute('SELECT content FROM facts ORDER BY id').fetchall()
    for r in rows:
        print(f"   • {r[0][:70]}")
    conn.close()
    return count


def cleanup():
    """Supprime la table user_facts créée par erreur dans V9 DB."""
    conn = sqlite3.connect(V9_DB)
    # Vérifier si elle existe
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_facts'"
    ).fetchone()
    if exists:
        conn.execute("DROP TABLE user_facts")
        conn.commit()
        print("✅ Table user_facts (erronée) supprimée de V9 DB")
    else:
        print("  ℹ️  Table user_facts déjà absente de V9 DB")
    conn.close()


def main():
    print("=" * 60)
    print("🌱  SEED PROFIL UTILISATEUR — NURU")
    print("=" * 60)
    
    cleanup()
    v = seed_v9_user_memory()
    i = seed_index_facts()
    
    print(f"\n{'=' * 60}")
    print(f"✅ TOTAL: {v + i} entrées dans les mémoires ({v} V9 + {i} index)")
    print("=" * 60)


if __name__ == "__main__":
    main()
