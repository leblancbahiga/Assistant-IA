# NURU V6 — Prochaine session

**Contexte** : Session du 5 juin 2026. 5 chantiers V6 implémentés et testés. 10 bugs critiques corrigés.

## 🎨 Chantier UI prioritaire : Refonte Cyber-Funk complète

6 étapes détaillées pour transformer l'interface en terminal d'assistant IA de science-fiction.

### Étape 1 — styles.qss
Remplacer par le thème Cyber-Funk :
- Fond `#0F0A1E`, IA `#FF00FF`, User `#39FF14`
- Scrollbars futuristes rose néon
- Sidebar `#0A0714` avec boutons `NavButton`
- Bulles : `ChatBubbleAssistant` bordure gauche rose, `ChatBubbleUser` bordure droite verte
- Input `QTextEdit#PromptInput` texte vert terminal
- ProgressBar chunk vert `#39FF14`

### Étape 2 — chat_bubble.py
Nouveau composant :
- `setObjectName("ChatBubbleUser"/"ChatBubbleAssistant")` pour QSS
- Entête : "VOUS" (vert) / "NURU SYSTEM" (rose)
- `append_text()` pour streaming
- `finalize_response()` pour post-traitement

### Étape 3 — Transitions fluides
- `switch_page()` dans `dashboard.py` : `QPropertyAnimation` + `QGraphicsOpacityEffect`, fondu 350ms, `OutCubic`
- `console_page.py` : `display_user_query()`, `start_assistant_response()`, `stream_token()`

### Étape 4 — Typing Effect (curseur clignotant)
Dans `chat_bubble.py` (assistant uniquement) :
- `QTimer` 500ms, curseur `█` clignotant
- `_toggle_cursor()` alterne texte + ` █` / texte seul
- `finalize_response()` arrête le timer et retire le curseur

### Étape 5 — Filtre de lisibilité (overlay fond.jpg)
Dans `styles.qss` :
- `#ChatContainer` avec `border-image: url(fond.jpg)`
- `QScrollArea#ChatScrollArea` : `background-color: rgba(15, 10, 30, 0.75)` (voile 75%)

### Étape 6 — circular_gauge.py
Jauges circulaires via `QPainter` :
- Cercle de fond `#2D2545`, arc néon couleur configurable
- Texte valeur centré + titre en dessous
- `set_value(0-100)` → `self.update()` (redessin)
- Utilisation : `ram_gauge = CircularGauge("RAM", "#39FF14")`

---

## 💎 Chantier technique prioritaire : CV → JSON structuré (Pydantic)

### Problème
Le RAG vectoriel est le mauvais outil pour les CV. Un CV est une base de données relationnelle (Candidat → Expériences → Rôles → Réalisations).

### Solution
Pipeline d'extraction LLM (Phi-4-mini ou Groq) qui transforme le CV en JSON structuré (Pydantic) avant indexation.

### Code de base
```python
from pydantic import BaseModel

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
5. Injection : quand l'utilisateur demande "mon CV", NURU injecte le JSON complet

### Fichiers concernés
- `src/cv_extractor.py` (NOUVEAU)
- `src/rag_engine.py` (+ table `cv_structured`)
- `reindex_full.py` (détection CV)
- `src/core/router.py` (route profil)

---

## 📋 Rappel des chantiers terminés

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
- ✅ Actions D (Idle Timer) + E (Budget post-template)

## 📁 Références
- Analyse OpenJarvis : `/Users/leblancbahiga/openjarvis_analysis.md`
- Analyse OpenHuman : `/Users/leblancbahiga/openhuman_analysis.md`
- Doc NURU V6 : `NURU-V6.md`

