# NURU V6 — Prochaine session : CV → JSON structuré (Pydantic)

**Contexte** : Session du 5 juin 2026 après-midi. 5 chantiers V6 implémentés et testés. 10 bugs critiques corrigés.

## État actuel

- ✅ TokenJuice (E1)
- ✅ Dual-Write / Nuru_Brain (E2)
- ✅ Learning Loop (E3) — avec Idle Timer 5min
- ✅ Auto-Fetch (E4)
- ✅ Stratégies Hybrides (E5)
- ✅ Profile Boost
- ✅ V2 Chunking hiérarchique (profils CV/Rapport/Note)
- ✅ Parent-Child Retrieval (table `chunk_hierarchy`)
- ✅ Budget token post-template (Action E)
- ✅ Seuils RAG dynamiques depuis settings.yaml
- ✅ 10 correctifs critiques

## 💎 Chantier prioritaire restant : CV → JSON structuré

### Problème
Le RAG vectoriel est le mauvais outil pour les CV. Un CV est une base de données relationnelle (Candidat → Expériences → Rôles → Réalisations). Le chunker V2 résout la fragmentation mais ne structure pas l'information.

### Solution
Pipeline d'extraction LLM (Phi-4-mini ou Groq) qui transforme le CV en JSON structuré (Pydantic) avant indexation.

### Code de base (à adapter)

```python
from pydantic import BaseModel
from typing import Optional

class Experience(BaseModel):
    entreprise: str
    poste: str
    dates: str
    realisations: list[str] = []

class CVStructure(BaseModel):
    nom: str
    resume_global: str
    experiences: list[Experience] = []
    formations: list[str] = []
    competences: list[str] = []
```

### Actions
1. Créer `src/cv_extractor.py` — prend un texte brut, retourne `CVStructure`
2. Créer table `cv_structured` dans SQLite
3. Modifier `reindex_full.py` : si `is_cv(fname)`, bypass chunking, extraction JSON directe
4. Modifier `semantic_router.py` : route "Profil/CV" → interroge `cv_structured` directement
5. Injection : quand l'utilisateur demande "mon CV", "mon expérience", NURU injecte le JSON complet

### Fichiers concernés
- `src/cv_extractor.py` (NOUVEAU)
- `src/rag_engine.py` (+ table `cv_structured`)
- `reindex_full.py` (détection CV)
- `src/core/router.py` (route profil)

### Ressources
- Analyse OpenJarvis : `/Users/leblancbahiga/openjarvis_analysis.md`
- Analyse OpenHuman : `/Users/leblancbahiga/openhuman_analysis.md`
- Doc NURU V6 : `NURU-V6.md`
