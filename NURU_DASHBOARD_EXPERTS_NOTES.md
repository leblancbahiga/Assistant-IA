# NURU — Carnet de notes des rapports experts (Dashboard)

> Document de travail consolidant les recommandations des experts externes
> sur l'amélioration du dashboard NURU.
>
> **Méthode** : lecture intégrale de chaque rapport → extraction des points
> actionnables → filtrage senior (rejet / fusion / immédiat vs reporté).
>
> Auteur : Hermes (filtrage critique senior)
> Source projet : `/Users/leblancbahiga/Downloads/Assistant IA`
>

---

## Convention d'évaluation

Pour chaque point retenu, j'évalue :

- **P0 / P1 / P2** — Criticité (P0 = bloquant, P1 = qualité, P2 = nice-to-have)
- **Impact UX** — Fort / Moyen / Faible
- **Effort** — S (< 1h) / M (1-4h) / L (demi-journée-journée) / XL (multi-jours)
- **Conforme à l'architecture NURU ?** — ✅ / ⚠️ / ❌
- **Source** — Expert N° + section

**Règle de filtrage** :
- **Rejet sans hésitation** : gadget, doublon d'existant, contredit la Privacy-First,
  introduit une dépendance externe inutile, sera vite obsolète.
- **Fusion** : plusieurs experts convergent → je retiens la version la plus
  intégrée au code existant.
- **Acceptation immédiate** : corrige un bug reconnu, complète une lacune
  identifiée dans l'audit 7 experts (cf. `NURU_AUDIT_SYNTHESE.md` L1-L7).

---

## Rapports reçus (table de suivi)

| # | Expert / Source | Statut | Pages rapport | Note synthèse |
|---|-----------------|--------|---------------|---------------|
| 1 | UX/UI Senior (5 expertises, audit statique) | ✅ Lu intégralement | 1676 lignes | ⭐⭐⭐⭐ Très bon mais surdimensionné (77j-h) |
| 2 | UX/UI Senior reconception V11 (audit statique limité) | ✅ Lu intégralement | 1030 lignes | ⭐⭐⭐⭐ Plus ciblé sur chat/ergonomie, ROI plus net |
| 3 | Senior HCI expert (audit statique + patterns marché) | ✅ Lu intégralement | 268 lignes | ⭐⭐⭐ Philosophie "Context-First" précieuse, vision stratégique |
| 4 | UX/UI Senior Nielsen heuristics + accessibilité | ✅ Lu intégralement | 1062 lignes | ⭐⭐⭐⭐ Le + opérationnel : ROI chiffré, accessibilité WCAG détaillée, métriques avant/après |
| 5 | Expert UI/UX senior + Qt/PySide6 specialist | ✅ Lu intégralement | 231 lignes | ⭐⭐⭐⭐ Focus perf M1/8GB + QTextBrowser warning + Context Inspector pattern |

---

## Synthèse comparative Rapports N°1, N°2 vs N°3

| Aspect | Rapport N°1 | Rapport N°2 | Rapport N°3 |
|--------|-------------|-------------|-------------|
| Style | Académique exhaustif | Reconception chat-first | Stratégique + sémantique |
| Longueur | 1676 l (surdimensionné) | 1030 l (ciblé) | 268 l (synthétique) |
| Sidebar historique | ⚠️ évoqué | ✅ P0 Claim | ✅ P1 (Sprint 3) |
| Modèle architectural | Refonte UI V11 | Refonte V11 modes | **"Context-First"** ⭐ |
| @mentions | absent | ✅ P0 | ✅ P3 (split-view tardif) |
| Largeur max chat | absent | absente | **P0 critique UX** ⭐ (lisibilité 15-16") |
| Routeur dans bulle | header | header | **footer de la BULLE** ⭐ |
| Chat close-button toolbar | non | non | **Souris hover** ⭐ |
| Diagnostics = DevTools masqué | page standard | page Insights | **`Ctrl+Shift+I` à la Chrome** ⭐ |
| Docs en slide-over | page | grille | **right drawer** ⭐ |
| 1 page pour Docs+Mémoire | fusion avec tabs | fusion avec tabs | Split-view côte à côte | **Mémoire unifiée V5+V9** (R4 §6.2 #3) |
| **Accessibilité WCAG exhaustive** | absente | R2 §3.6 (6 items) | absente | **R4 §3 #1-5 + §10.6 : métriques avant/après détaillées** |
| **Métriques avant/après chiffrées** | absent | absentes | absentes | **R4 §10.6 (#clics 6→3, contraste 3.2→7.2, items 15→8, etc.)** ⭐ |
| **Activity Bar** VS Code style | absente | absente | absente | **R4 §6.2 #2 + Phase 7 sidebar 60px icônes-only** |
| **PlaceholderPages incohérence mapping** | non vu | non vu | non vu | **R4 §2 #3 : risque de pages vides** ⚠️ |
| **Placeholders réécriture métriques** | non | non | non | **R4 §6.2 #4, #10.3 : "CACHE Entries, Size, Recent, Oldest"** (refonte DataCard) |
| **Navigation 15→8 items** | oui | abstrait | abstrait | **R4 §7 #2.1 : Activity Bar 5 items + footer 2** | **R5 §6 : 3 espaces (Workspace/Knowledge/System)** |
| **Inspector Panel** right-dock (`QDockWidget`) | RightPanel existant | RightPanel existant | RightPanel existant | R4 inexistant | **R5 §4 #2 + §7 wireframe : Volet inspection rétractable** ⭐ |
| **QTextBrowser warning** (perf HTML rendering) | absent | absent | absent | absent | **R5 §2 faiblesse + §5 #4 : éliminer QTextBrowser au profit de widgets natifs** ⭐ |
| **Status stream async** Agent/RAG/Routeur | absent | thinking block | RAG timeline | absent | **R5 §5 #3 : `[✓] Routage → [⚡] RAG → [...] Génération`** ⭐ |
| **Inspecteur RAG dans la bulle** vs dans une page tierce | non | SourcePreview popup | non | non | **R5 §2 faiblesse critique : « casse le flow »** |
| **Mémoire V9 graph visualisation** | rejetée | rejetée | rejetée | rejetée | **R5 §7 wireframe Knowledge Base le remet (mais à valeur)** |
| **Rejet palette Tailwind** R3/R4 vs **palette custom** R5 | Tailwind | Deep Ocean (garder) | Custom | Tailwind | **R5 §8 nouvelle palette sobre `#121214/#3B82F6`** — conflit à arbitrer |

### Ce que le Rapport N°3 ajoute **que les 2 autres ratent** :

1. **Philosophie "Context-First" / "Core Chat + Contextual Panels"** — l'utilisateur pense en intention ("Vérifier cette source", "Voir le doc lié"), pas en screen ("Page Documents"). Avant : on demande à l'utilisateur de naviguer. Après : le contexte vient à lui (right drawer slide-in, split-view contextuel).

2. **Largeur max du chat (768px centré, `margin: 0 auto`)** — non mentionné par R1/R2 mais **fondamental pour 15-16"** : sans ça, sur 16", la bulle fait 2000px de large et la ligne de texte perd toute lisibilité. C'est une lacune UX silencieuse mais quotidienne.

3. **Routeur dans le footer de la BULLE** (pas dans le header global) — meilleure granularité : chaque réponse dit de quel modèle elle vient, pas le dernier état global.

4. **Distinction visuelle hallucination vs citation vérifiée** (Vert=OK, Orange=incertain, Rouge=contredit) — couleur différente par status, liée au FactChecker qui existe déjà. Le **Fact Checker V8+ est déjà câblé**, c'est juste de l'affichage.

5. **DevTools masqué `Ctrl+Shift+I`** — pattern Chrome/VS Code, déplace Diagnostics du flux principal vers un outil power-user. Cohérent avec notre "ne pas surcharger l'utilisateur solo".

6. **Documents comme slide-over / panel contextuel** — pas une page dédiée. Le contexte du doc n'apparaît QUE quand l'utilisateur travaille dessus ou demande une source.

7. **Elévation/shadows manquants dans le thème Dark** — point visuel subtil mais qui distingue "Qt natif années 2010" d'une "app moderne 2025". Très peu coûteux (QSS box-shadow Qt 5.15+).

8. **Citation `[1][2]` cliquables inline dans le texte** (style Perplexity) — NURU met `[Source: doc.pdf]` aujourd'hui, mais le R2 notait que c'est "buried" dans la bulle. Passer à `[1]` inline avec popup = bien plus lisible.

### Items rejetés spécifiques au R3

| ID | Élément rejeté | Justification |
|----|----------------|---------------|
| REJ-R3-1 | **"Workspaces" / "Espaces de travail"** (multi-projets séparés avec isolation) | Leblanc = solo dev, ses "projets" sont des sessions, pas des workspaces étanches. SessionStore suffit. |
| REJ-R3-2 | **Split-view Documents/Mémoire permanent côte à côte** | Trop rigide (cf. cursor). Le slide-over est mieux : apparaît quand on en a besoin, disparaît sinon. |
| REJ-R3-3 | **RAG highlight dans aperçu PDF** (P3 estimé "très élevé") | Nécessite un viewer PDF custom. Trop pour le sprint. Reporter à V11.4+. |
| REJ-R3-4 | **Séparer theme_manager.py** distinct | Les tokens QSS suffisent dans `styles.qss`. Pas besoin d'un module Python dédié. |

### Ce que le Rapport N°4 ajoute **que les 3 autres ratent** :

1. **Métriques avant/après chiffrées** — `§10.6` :
   - Clics max pour tâche basique : 6 → 3 (-50%)
   - Items navigation : 15 → 8 (-47%)
   - Contraste texte nav : 3.2:1 → 7.2:1 (WCAG AA → AAA)
   - Taille police min : 9px → 12px (respecte WCAG 1.4.4)
   - Temps tâche basique : 45s → 15s (-67%)
   **Utile pour la roadmap** — permet de mesurer le succès de V11.

2. **Bug latent critique : `PLACEHOLDER_PAGES` incohérent** — `§2 #3` : le code mentionne
   `PLACEHOLDER_PAGES["sessions"]`, `["documents"]`, etc. avec des labels, mais les **vraies
   pages existent déjà** dans `components/`. Risque = si le mapping échoue, l'utilisateur
   tombe sur un placeholder vide. **À vérifier systématiquement** lors du sprint V11.1.

3. **Activity Bar style VS Code (60px icônes-only)** — `§6.2 #2`. Plus radical que mon P0-C
   (collapse sidebar 220↔64). À considérer comme **option B**: icônes fixes en permanence
   + drawer qui slide pour révéler les labels. Décision utilisateur.

4. **Refonte des DataCards dans RightPanel** — `§6.2 #4`, `§10.3 calcul métriques CACHE`
   propose : Entries, Size, Recent, Oldest. C'est plus riche que la StatCard actuelle.
   Note : fusionne naturellement avec mon **P0-G Unifier StatCard**.

5. **Solutions accessibilité avec valeurs exactes** — `§3` :
   - Police mini `9px → 12px` (= 11px d'origine ACC-1 confirmé)
   - Contraste nav `#4A6080 (3.2:1) → #7A9ABF (5.8:1)` (valeur hex fournie)
   - Boutons : unifier `28/30/34/36px → 32px` (valeur unique)

6. **Notification system** — `§6.2 #4` ajoute 4 exemples concrets : "Document indexé",
   "Mémoire saturée", "Cloud connecté", "Erreur d'indexation". À utiliser comme
   dictionnaire d'événements pour démarrer le système Toasts (P1-B).

### Items rejetés spécifiques au R4

| ID | Élément rejeté | Justification |
|----|----------------|---------------|
| REJ-R4-1 | **Toggle thème clair/sombre** (Priorité 1, ROI élevé) | **Identité NURU = dark premium**, déjà refusé R3. Reporter à hypothétique V12. |
| REJ-R4-2 | **Onboarding interactif** (4.4, 3j) | Leblanc = solo dev qui connaît déjà son outil. Sur-investissement UX. |
| REJ-R4-3 | **RAG Explorer visualisation** (3.2, 6j) | Cf. R1 #9 visualisations exotiques — sur-engineering pour solo. |
| REJ-R4-4 | **Memory Timeline visualisation** (3.5, 3j) | Le SessionStore fournit déjà l'historique, un graphe est gadget. Reporter. |
| REJ-R4-5 | **Quick Settings Panel** (3.4, 2j) | Le model switcher header (P0-E) + chip routage (P1-G) couvrent déjà l'essentiel. |
| REJ-R4-6 | **"Appliquer 3B82F6 / 10B981 palette Tailwind standard"** | Couleurs non alignées avec "Deep Ocean" actuel (=#1A6A9A). Migration risquée pour gain esthétique mineur. **Garder la palette R2 (13 tokens + grille 4px)**. |
| REJ-R4-7 | **8 semaines de planning** | Idem R1 : irréaliste solo. Garder ma structure 1 sprint = 1 jour. |

### Ce que le Rapport N°5 ajoute **que les 4 autres ratent** :

1. **⚠️ QTextBrowser = goulot d'étranglement perf** — `§2 faiblesse + §5 #4`.
   Le `chat_bubble.py` actuel (rapport 1) **utilise des `setStyleSheet()` + héritage QFrame**,
   pas QTextBrowser, mais l'audit R5 cible aussi **le rendu HTML du QTextBrowser** présent
   dans `messages_area` pour certains types de messages markdown. **Action** : auditer le
   code avec `grep "QTextBrowser" src/ui/` lors du pré-check.

2. **Status stream async Agent Step-by-Step** — `§5 #3` :
   `[✓] Routage de l'intent` ➔ `[⚡] Recherche RAG` ➔ `[...] Génération`. C'est une
   Killer feature V8+ qui existe **dans l'orchestrateur** (events : `rag_score`,
   `verification_warning`, `query_decomposed`, `generation_complete`) mais n'est
   pas affichée de manière séquentielle à l'utilisateur. À câbler dans la bulle
   en cours via l'EventBus → blocs successifs qui se remplissent.

3. **Context Inspector pattern** — `§4 #2`. R5 parle d'un panneau latéral droit
   d'inspection `QDockWidget` déjà présent dans NURU. Mais R5 l'appelle
   différemment : "Volet d'inspection contextuelle rétractable" qui affiche les
   **détails de l'inférence courante** au moment où la réponse s'écrit. Plus
   dynamique que mon RightPanel existant (qui montre des métriques statiques).
   → À voir dans V11.2 si on garde les 2 ou si on fusionne.

4. **3 espaces de travail** au lieu de 8 pages — `§6` :
   - **Workspace** = chat + inspection
   - **Knowledge** = documents + mémoire V9
   - **System** = modèles + diagnostics + paramètres+ logs
   C'est **plus radical que mon P0-B** (5 sections). R5 propose 3. Mais c'est
   probablement trop radical pour V11.1 — on garde le 5-sections en V11.1, on
   envisage la fusion 3-espaces en V11.4.

5. **Drag&Drop dans la zone d'input** + auto-complétion `@` — `§5 #1`.
   Convergent avec R2 et R3 (@mentions). R5 précise en plus : **auto-expansion
   verticale du QTextEdit** selon contenu, et **badge visuel** du fichier attaché.
   Pratique code pour `SmartTextEdit` existe déjà via V4 console_page.

6. **Pas de QMessageBox bloquante pour les erreurs** — `§4 #5`. Convergence
   avec mon P1-B Toasts. R5 insiste : "brise l'expérience utilisateur". À
   coder en PRIORITÉ pour la stabilité UX.

7. **Refactor UI → `ui/pages/` + `ui/components/` distincts** — `§10`.
   Différent de l'actuel : on a déjà `src/ui/components/` mais pas
   `src/ui/pages/`. R5 propose de migrer les pages dans un sous-dossier dédié
   pour clarifier l'architecture. **GROS refactor**, ne pas faire en V11.1
   sauf si d'autres refontes l'exigent.

### Items rejetés spécifiques au R5

| ID | Élément rejeté | Justification |
|----|----------------|---------------|
| REJ-R5-1 | **Palette `#121214/#3B82F6`** (Tailwind-ish) | NURU a sa propre identité "Deep Ocean" `#0A0E14/#1A6A9A`. Migration risquée. Garder R2 §9 sauf si redesign complet. |
| REJ-R5-2 | **3 espaces (Workspace/Knowledge/System)** comme refonte immédiate | Trop radical pour V11.1. À envisager en V11.4 si l'utilisateur le demande. |
| REJ-R5-3 | **Graph V9 émotionnel/logique** dans Knowledge | Sur-engineering (déjà rejeté R1, R3). Le wireframe est joli mais demande un moteur de graphes. |
| REJ-R5-4 | **Refactor structurel** `ui/pages/` + `ui/components/` split | Backward-incompatible. Reporter à V11.4 ou plus tard. |
| REJ-R5-5 | **Fusion RAG Explorer + Mémoire V9 graph** = 5 jours | Idem rejet R3, R4 — sur-engineering. On garde la fusion Memory V8+V9 simple (P1-D). |

---
---

## Synthèse globale — Rapport N°1

**Verdict de l'expert** : NURU V10.2 = "système d'IA exceptionnel, interface qui ne le révèle pas. L'utilisateur voit 20% de la puissance."

**Points forts de l'audit** (que je valide) :
- Code bien analysé (14 366 lignes, 64 classes, design system dispersé identifiés)
- Constat technique exact (5 bleus hardcodés, pages orphelines, doublons)
- Wireframes ASCII utiles comme spec
- Tableau ROI clair

**Faiblesses de l'audit** (que je corrigerai) :
1. **77 jours-homme sur 4 sprints** — irréaliste pour un dev solo. Découpage à revoir.
2. **Refonte V11 globale** proposée — trop risquée. Préférer **incréments visibles**.
3. **Pas hiérarchisé** l'impact vis-à-vis du code existant (qui aurait pu être réutilisé).
4. **Confond "V11 refonte UX" avec "réécriture from scratch"** — gros risque d'écraser ce qui marche.
5. **Aucune corrélation avec l'audit 7 experts** (`NURU_AUDIT_SYNTHESE.md`) — on a déjà identifié les lacunes L1-L7, ce rapport les redécouvre sous un autre angle sans s'y référer.

---

## Points experts — extraction brute (Rapport N°1)

### 🔴 P0 — Quick wins (impact fort, effort faible/modéré)

| ID | Point expert | Source |
|----|--------------|--------|
| P0-A | Supprimer pages doublons (Mémoire, Stats, Modules) | R1 §2.1 P1.2, §7.2 / R2 §7.3 |
| P0-B | Renommer sidebar (logique user, pas version) | R1 §2.1 P1.3, §7.2 |
| P0-C | Sidebar collapsible (220 ↔ 64 px) | R1 §3.3, §6.1 / R2 §3.1-3.2, §7 |
| P0-D | Drag & drop fichiers sur chat | R1 §4.1 / R2 §6.1 |
| P0-E | Model switcher dans header | R1 §5, §6.1 / R2 §6.2 |
| P0-F | Supprimer/recaser 1000+ lignes de code orphelin | R1 §1.4, Annexe B / R2 §7.3 |
| P0-G | Unifier 5 variantes de StatCard / 6 variantes de Badge | R1 §3.2 |
| **P0-H** | **MessageActions sur chaque bulle** (👍/👎 + 📋 + 🔄 regenerate + ✏️ edit + 🗑 delete) | **R2 §3.2 #13-15, §6.2** ⚠️ absent du R1 |
| **P0-I** | **RightPanel collapsible** (R2 §3.2 #7-8 → 21% écran perdu) | **R2 #34** |
| **P0-J** | **Sidebar avec historique conversations** (le code SessionStore V10.3f est déjà prêt, il manque l'UI) | **R2 §6.1 #1, §6.2 #11** |
| **P0-K** | **Contrainte `max-width: 768px; margin: 0 auto`** sur la zone de chat centrale | **R3 Phase 3 + §6 #6** ⚠️ absent R1/R2 |
| **P0-L** | **DevTools masqué `Ctrl+Shift+I`** pour Diagnostics (pattern Chrome/VS Code) | **R3 §10.6 #5** ⚠️ absent R1/R2 |
| **P0-M** | **Citations `[1][2]` cliquables inline dans le texte** (style Perplexity) | **R3 §10.6 #2** ⚠️ absent R1/R2 |
| **P0-N** | **Routeur modèle dans le footer de CHAQUE bulle** (au lieu du header global) | **R3 §5 + §6.6 #2** ⚠️ absent R1/R2 |
| **P0-O** | **Distinction visuelle status FactChecker** : surbrillance Vert/Orange/Rouge des passages | **R3 §5 Fact Checker** ⚠️ absent R1/R2 |

### 🟡 P1 — Fondations (impact fort, effort moyen/fort)

| ID | Point expert | Source |
|----|--------------|--------|
| P1-A | Cmd+K recherche universelle | R1 §6.1, §7.7 / R2 §6.2 |
| P1-B | Toast notifications (feedback moderne) | R1 §6.6, §6.8 / R2 §6.2 #17 |
| P1-C | Design system tokens (couleurs/spacing/typo) — palette R2 13 tokens + grille 4px | R1 §3.1, §3.2 / R2 §9.1-9.3 |
| P1-D | Fusionner Mémoire V8 + V9 (tabs par type) | R1 §7.7 / R2 §7.3 |
| P1-E | Fusionner Stats + Diagnostics (page Performances / Insights unique) | R1 §7.9 / R2 §7.3 |
| P1-F | Fusionner AgentStatus + TaskList (Agent Live) | R1 §7.8 / R2 §7.3 |
| P1-G | Indicateur de routage dans header (RAG/LOCAL/CLOUD/WEB) | R1 §5, §6.9 / R2 §5 |
| P1-H | Quick action chips sous input (Résumer, Traduire, Chercher) | R1 §6.1, §7.5 / R2 §6.1 #5 |
| P1-I | Streaming cursor visuel (bubble en cours) + TypingIndicator avec VRAIES stratégies | R1 / R2 #11 |
| P1-J | Dashboard d'accueil avec KPIs | R1 §7.4 |
| P1-K | Markdown rendering riche (code blocks, tables) | R1 §4.1, §6.1 / R2 |
| **P1-L** | **@mentions** (documents, mémoire, web) —killer feature NURU, mémoire V9 sous-exploitée | **R2 §3.2 #15, §6.1 #4, §10.2 #5** |
| **P1-M** | **ThinkingBlock expand/collapse** dans les bulles — raisonnement V8+ déjà collecté | **R2 §3.2 #6, §6.2 #15** |
| **P1-N** | **SourcePreview** sur hover des citations (snippet 200 chars) | **R2 §6.2 #16, #R2 §11.5** |
| **P1-O** | **Focus mode** (plein écran chat, hide sidebar+panel) | **R2 §10 Phase 2 #10** |
| **P1-P** | **TimelineRouting** dans le panel droit ("Intent → RAG → 3 sources → LLM → response") | **R2 §5, §10.2** |

### 🟢 P2 — Polish (impact moyen, à programmer après P0+P1)

| ID | Point expert | Source |
|----|--------------|--------|
| P2-A | Settings simplifié (sidebar interne, recherche/filtre) | R1 / R2 §14 |
| P2-B | Skeleton loaders | R1 / R2 §10 Phase 4 #18 |
| P2-C | Empty states / error states travaillés | R1 / R2 §6.4 |
| P2-D | Animations de transition entre pages | R1 / R2 |
| P2-E | Raccourcis clavier (Cmd+1..9, Cmd+/ pour sidebar, Cmd+K cmd palette) | R1 / R2 §6.1 #7 |
| P2-F | RAG chunk preview (200 chars around match) | R1 / R2 — fusionné avec P1-N |
| P2-G | Memory graph des connexions entre faits | R1 / R2 §11.5 (⚠️ élevé, P2) |
| P2-H | Multi-format export (MD, JSON, PDF) | R1 / R2 §6.1 #8, §10 Phase 4 #19 |
| **P2-I** | **Numérotation messages** (timestamps visibles sur les bulles, R2 §3.2 #12) | **R2 #12** |
| **P2-J** | **Historique prompts flèches haut/bas** dans l'input (R2 §3.2 #10) | **R2 #10** |
| **P2-K** | **ProjectList sidebar groupé A→Z** (utile multi-sujets) | **R2 §7.4** |
| **P2-L** | **3-mode toggle** (Chat / Focus / Document) — Focus est trivial, Document = split view non trivial, garder seulement 2 modes | **R2 §7.4** (P2 — split view lourd) |
| **P2-M** | **Tokens QSS unifiés** dans `styles.qss` (`--color-bg-primary`, etc.) | **R3 §10.9 #1** |
| **P2-N** | **Elévation/shadows** dans le thème Dark (box-shadow Qt 5.15+) | **R3 §3 + §10.9** |
| **P2-O** | **Right drawer slide-over** pour Documents/Sources contextuels (vs page dédiée) | **R3 §10.7 #2 + §7** |

### ♿ P0/P1 Accessibilité (transverse, R2 §3.6 + R4 §3)

| ID | Problème WCAG | Source | Valeur cible |
|----|---------------|--------|---------------|
| ACC-1 | Texte 9px → minimum 12px | R2 #39 / R4 §3 #2 | **12px mini** |
| ACC-2 | Couleur nav `#4A6080` contraste 3.2:1 → minimum 4.5:1 | R2 #40 / R4 §3 #1 | `#7A9ABF` (5.8:1) |
| ACC-3 | Pas de focus indicators visibles (:focus généralisé dans QSS) | R2 #41 / R4 §3 #3 | outline visible state focus |
| ACC-4 | Emojis comme seuls labels (🎙📎🛡↑) → ajouter `setAccessibleName` | R2 #42 / R4 §3 #5 | objectName + accessibleName |
| ACC-5 | QTabWidget sans accessible name | R2 #44 | setAccessibleName + tab role |
| ACC-6 | Bootstrap `theme_select` qui ne change rien (settings_page) | R2 #30 | retirer ou implémenter |
| **ACC-7** | **Boutons tailles inconsistantes** 28/30/34/36px → **32px uniform** | **R4 §3 #3** ⭐ | 32px |
| **ACC-8** | **Contrast global muted texte** `#3D5266 (2.1:1)` → min 4.5:1 | **R4 §3** | `#7A9ABF` ou `#8BA3B8` |

### ❌ Rejetés d'office (avec justification)

| ID | Élément rejeté | Justification |
|----|----------------|---------------|
| REJ-1 | **Refonte V11 globale from-scratch** | On a 14 366 lignes UI qui marchent. Risque de régression énorme. Sprint incrémental uniquement. |
| REJ-2 | **Light theme (A20)** | NURU est "100% local, premium dark, 8GB RAM". Light theme incohérent avec l'identité produit. Reporter. |
| REJ-3 | **Mobile-responsive (A29)** | NURU = desktop natif PySide6. Pas de cible mobile. Effort 10j pour 0 valeur. |
| REJ-4 | **Avatar upload** | Gadget pour un assistant solo. |
| REJ-5 | **Bookmarks sur messages** | Doublon fonctionnel avec Feedback 👍 + Mémoire V9. |
| REJ-6 | **Mode focus / lecture** | Nice-to-have très礼品, ROI faible. Push après V11. |
| REJ-7 | **Prompt templates library (A21)** | Dépend du use-case. Leblanc = solo dev. Reporter jusqu'à demande explicite. |
| REJ-8 | **CostWidget (Cloud $)** | NURU = local-first, gratuit. Coût cloud marginal. |
| REJ-9 | **Marketing/visualisations exotiques** (heatmap, word cloud, radar compétences, sankey) | Sur-engineering pour un dev solo. Le RightPanel actuel suffit. |
| REJ-10 | **Pin conversations en haut sidebar** | SessionStore + auto-titrage V10.3g font déjà le job. Doublon. |

---

# 🏁 Sprint V11.1 — Quick wins (P0) — TODO immédiatement

**Périmètre limité** — uniquement ce qui produit un changement visible immédiat
**sans toucher au pipeline backend** :

**⚠️ Pré-check R4 critique** : AVANT de toucher quoi que ce soit, vérifier
que l'index `PLACEHOLDER_PAGES` dans `dashboard.py` mappe correctement vers
les **vraies pages** dans `components/`. Risque : page vide affichée à
l'utilisateur si le slug est mal orthographié. Bug latent cité par R4 §2 #3.

**⚠️ Pré-check R5 critique** : `grep -rn "QTextBrowser" src/ui/`
pour identifier les zones où le rendu HTML pourrait pénaliser les perfs M1.
Les bulles de chat actuelles utilisent QFrame (cf. R1) — donc OK,
mais le `messages_area` ou le rendu markdown pourrait en contenir.

1. **P0-B Renommer sidebar** — remplacer "Principal/Connaissances/NURU V9/Système/NURU V10"
   par "Accueil/Discussions/Connaissances/Assistant/Plus". → **0.5j** ✅
2. **P0-J Sidebar avec historique conversations** — `SessionStore.list_sessions()`
   existe déjà (V10.3f), il suffit d'un `QListWidget` dans la sidebar qui lit
   la table SQLite. Auto-titrage déjà câblé V10.3g. → **0.5j** ✅ leader
3. **P0-F Supprimer orphelins** : `guides_page.py` (542), `FeedbackBar` widget,
   `TelemetryViewModel`, `ContextViewModel` (vérifier qu'aucun dashboard ne les utilise).
   Si orphelin confirmé → delete + commit. → **0.5j** ✅ leader
4. **P0-K Contrainte `max-width: 768px; margin: 0 auto`** sur le conteneur de chat.
   Fix visuel d'1 ligne CSS, impact immédiat sur 15-16". → **S** ⚡ quick win R3
5. **P0-C + P0-I Collapse sidebar ET right panel** — bind `Cmd+/` panel, `Cmd+\` sidebar.
   États par défaut = étendus. Mémoriser dans app_state. → **1j**
6. **P0-H MessageActions** — ajouter 📋 Copy (1h, déjà plupart du code),
   🔄 Regenerate (signal vers orchestrateur, 2h),
   ✏️ Edit message user (rewrite query + replay, 3h).
   Plus simple et plus impactant que de nombreuses features P1. → **1j**
7. **P0-N Routeur modèle dans le footer de CHAQUE bulle** — chaque réponse dit
   explicitement son modèle source (`🧠 phi-4-mini-4bit · LOCAL` / `☁️ Groq llama`).
   Code déjà calculé V8+, juste affichage. → **M**
8. **P0-E Model switcher dans header** — afficher runtime model + badge local/cloud.
   Lutte contre L5 (hallucinations non mesurées). → **1j**
9. **P0-G Unifier `StatCard`** — créer `src/ui/components/stat_card.py` unique,
   remplacer les 4 variantes actuelles (right_panel, feedback, stats, memory).
   Haute valeur car chacun des 4 modules touchés est déjà un point d'entrée
   observé par l'utilisateur. → **1j**

**Total V11.1 estimé** : ~5 jours-homme. **1 sprint d'une journée**.

> **Note méthodologique R3** : la philosophie "Context-First" (P3-N slide-over,
> P3-L DevTools Ctrl+Shift+I) **ne sera PAS dans V11.1** — ce sont des refontes
> de navigation qui méritent un sprint dédié V11.2b après stabilisation.
>
> **Note R4** : l'**Activity Bar** (option B sidebar 60px icônes-only) est plus
> radicale que mon **P0-C collapse 64px**. Décision à valider avec toi avant
> V11.2 — soit on garde l'option A (collapse classique), soit on migre vers
> Activity Bar style VS Code. Laquelle préfères-tu ?

### 🏗️ Sprint V11.2 — Fondations (P1) — Après validation V11.1

1. **P1-G Indicateur routage dans header** — petit chip à côté du titre :
   `🧭 FAQ` / `🌐 Web` / `📚 RAG` / `💻 Local` / `☁️ Cloud` — code déjà câblé V8+
2. **P1-P TimelineRouting** dans le right panel — explicite "Intent → RAG → 3 sources → Réponse"
3. **P1-L @mentions** (auto-complétion documents/mémoire/web dans le SmartTextEdit)
   — killer feature qui exploite vraiment la mémoire V9 à 6 types
4. **P1-M ThinkingBlock expand/collapse** dans les bulles — révèle le raisonnement V8+
5. **P1-H Quick action chips** sous l'input : `📝 Résumer · 🌐 Traduire · 📚 Chercher docs · 💡 Aide`
6. **P1-I Streaming cursor visuel + TypingIndicator avec VRAIES stratégies**
   (le widget existe déjà mais l'expert N°2 note "RECHERCHE MULTI-STRATÉGIE · 1/3" est mock)
7. **P1-D Fusion Mémoire V8+V9** — `MemoryPage` avec tabs (6 types V9)
8. **P1-E Fusion Stats + Diagnostics** — page **Performances** unique
9. **P1-O Focus mode** (Plein écran chat, un toggle `Cmd+F`) — trivial
10. **P1-B Toasts** — système unifié non-bloquant (4 niveaux) — **priorité R5 : remplace QMessageBox bloquante**
11. **🆕 Status stream async R5** — pendant réponse, blocs successifs se remplissent :
    `[✓] Routage` → `[⚡] RAG` → `[...] Génération` → `[⏸] Fact-check`.
    EventBus existe déjà (V8+) : `rag_score`, `query_decomposed`,
    `verification_warning`, `generation_complete`. **Câbler les events → UI Stream**.
12. **ACC-1..ACC-8 Accessibilité transverse** — police mini 12px, contraste 4.5:1, focus indicators, setAccessibleName, boutons 32px. **À faire en parallèle de V11.2**, pas un sprint dédié

### ⏸️ Sprint V11.3a — Polish (P2) — À planifier après V11.2

Cmd+K, Markdown rendering (P1-K), Skeleton loaders, Empty states,
Raccourcis clavier (P2-E), Memory graph connections (P2-G),
Numérotation messages (P2-I), Historique prompts ↑/↓ (P2-J).

### ⏸️ Sprint V11.3b — Features avancées — À planifier après user validation

Dashboard d'accueil (P1-J), P1-C Design system tokens, Settings simplifié (P2-A),
P1-N SourcePreview, ProjectList sidebar (P2-K), Export multi-format (P2-H).

---

## Notes critiques à valider avec Leblanc avant implémentation

⚠️ **Avant de coder, j'ai besoin de ta décision sur 4 points** :

1. **Refonte sidebar** — je propose le découpage "Accueil / Discussions /
   Connaissances / Assistant / Plus" (cf. §7.2 de l'audit). Validé ou tu veux
   autre chose ?

2. **Pages supprimées** — j'ai listé ce qui peut disparaître (Guides 542l,
   ToolTester 717l, Architecture 383l, SystemPage 501l = ~2100 lignes).
   OK pour **archivage** ou **suppression définitive** ? (Recommandation : archiver
   dans `_archive/` au cas où, puis supprimer.)

3. **Modèle de livraison** — le rapport propose 4 sprints de 2 semaines chacun
   (77j cumulés). Pour un dev solo, je propose **1 sprint = 1 jour**, pas plus,
   et on itère "1 chose visible à la fois" (méthode V10.x). D'accord ?

4. **Risque regression** — la sidebar V10.2 est utilisée par tous les flux de
   navigation. Toute refonte UI doit être **testée sur macOS** avant commit.
   Quel process : (a) tu lances toi-même entre chaque patch, (b) je propose
   des tests `pytest-qt` minimaux par page ?

5. **Activity Bar (option B) vs Collapse classique (option A)** — **ajoutée
   après R4** §6.2. L'audit propose un sidebar 60px icônes-only permanent
   (style VS Code), plus radical que mon collapse 220↔64px. Tu préfères :
   - **Option A** : sidebar 220 pleine, collapse vers 64px au clic
   - **Option B** : sidebar 60 icônes-only permanent, drawer pour labels
   - **Option C (hybride)** : mode "Apprenti" en A par défaut, "Expert" en B activable

6. **Light theme (question R4) — confirmée mon rejet** — NURU reste 100% dark.
   Mais R4 note 2.2 (#clics 6→3) un gain sur la navigation. OK pour abandonner
   le light theme au profit du focus sur la nav ?

---

## 📊 SYNTHÈSE EXÉCUTIVE FINALE — 5 rapports consolidés

### Convergences fortes des 5 rapports (≥4 sur 5)

| Item | R1 | R2 | R3 | R4 | R5 | Sprint retenu |
|------|----|----|----|----|----|---------------|
| Supprimer pages orphelines | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.1 #3** |
| Renommer sidebar (logique user) | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.1 #1** |
| Sidebar avec historique conversations | ⚠️ | ✓ | ✓ | ✓ | ✓ | **V11.1 #2** |
| Collapse sidebar+panel | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.1 #5** |
| Model switcher header | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.1 #8** |
| MessageActions (edit/regen/copy) | ✗ | ✓ | ✗ | ⚠️ | ✓ | **V11.1 #6** |
| Indicateur routage header | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.2 #1** |
| @mentions documents/mémoire | ✗ | ✓ | ✓ | ⚠️ | ✓ | **V11.2 #3** |
| ThinkingBlock expand | ⚠️ | ✓ | ✗ | ✗ | ✗ | **V11.2 #4** |
| Toasts non-bloquants | ✓ | ✓ | ✓ | ✓ | ✓ | **V11.2 #10** ⚡ |
| Routage dans bulle (footer) | ✗ | ✗ | ✓ | ✗ | ✓ | **V11.1 #7** |
| Largeur max chat 768px | ✗ | ✗ | ✓ | ✗ | ✗ | **V11.1 #4** ⚡ |
| Suppression QMessageBox bloquante | ✗ | ✗ | ✗ | ⚠️ | ✓ | **V11.2 #10** |
| Status stream async agent steps | ✗ | ⚠️ | ⚠️ | ⚠️ | ✓ | **V11.2 #11** 🆕 |
| Pré-check PLACEHOLDER_PAGES | ✗ | ✗ | ✗ | ✓ | ✗ | **V11.1 pré-check** |
| Pré-check QTextBrowser perf | ✗ | ✗ | ✗ | ✗ | ✓ | **V11.1 pré-check** |

### Items rejetés (consensus ≥3 rapports)

| Item rejeté | R1 | R2 | R3 | R4 | R5 | Justification |
|-------------|----|----|----|----|----|---------------|
| Light theme | ✗ | ✗ | ✗ | ✓ | ⚠️ | Identité NURU dark = OK |
| Mobile responsive | ✗ | ✗ | ✗ | ✗ | ✗ | Desktop natif PySide6 |
| Marketplace / Workspaces | ✗ | ✗ | ⚠️ | ✗ | ✗ | Solo dev, sessions suffisent |
| Memory graph / Knowledge graph | ✓ | ⚠️ | ✗ | ✓ | ✓ | Sur-engineering |
| RAG Explorer visualisation | ⚠️ | ✗ | ✗ | ✓ | ⚠️ | Sur-engineering |
| Onboarding interactif | ✗ | ✗ | ✗ | ✓ | ✗ | Solo dev, connaît son outil |
| Palette Tailwind standard | ⚠️ | ⚠️ | ⚠️ | ✓ | ✓ | "Deep Ocean" R2 §9 garde |
| Avatar upload | ✗ | ✗ | ✗ | ✗ | ✗ | Gadget solo |
| CostWidget (Cloud $) | ✗ | ✗ | ✗ | ✗ | ✗ | NURU local = gratuit |
| Refonte "from scratch" V11 | ✓ | ✓ | ⚠️ | ✓ | ⚠️ | Risque régression énorme |

### Métriques cibles (R4 §10.6 — à mesurer avant/après V11)

| Métrique | Actuel | Cible V11.1+ | Méthode de mesure |
|----------|--------|--------------|-------------------|
| Items navigation | 15 | 8 (-47%) | Compter QPushButton dans NavSidebar |
| Clics max tâche basique | 6 | 3 (-50%) | Prendre un scénario RAG + chrono |
| Contraste texte nav | 3.2:1 | 7.2:1 | Outil WebAIM Contrast Checker |
| Police mini | 9px | 12px (WCAG) | grep sur styles.qss |
| Temps tâche basique | 45s | 15s (-67%) | Chrono manuel Leblanc |

---

## Sprint V11.1 final (mis à jour synthèse 5 rapports)

**9 items + 2 pré-checks, ~5 jours-homme, 1 sprint = 1 jour**

| # | Étape | Source | Effort |
|---|-------|--------|--------|
| 0a | ⛔ Pré-check `PLACEHOLDER_PAGES` mapping | R4 §2 #3 | S |
| 0b | ⛔ Pré-check `grep QTextBrowser src/ui/` | R5 §5 #4 | S |
| 1 | P0-B Sidebar renommée 5 sections | R1+R2+R3+R4 | 0.5j |
| 2 | P0-J Sidebar historique conversations | R2+SessionStore V10.3f | 0.5j |
| 3 | P0-F Suppression orphelins (4 fichiers) | R1 | 0.5j |
| 4 | P0-K `max-width: 768px; margin: 0 auto` chat | R3 ⭐ | 5min |
| 5 | P0-C+I Collapse sidebar+panel | R1+R2 | 1j |
| 6 | P0-H MessageActions (Copy/Regen/Edit) | R2 | 1j |
| 7 | P0-N Routeur footer de bulle | R3+R5 | 0.5j |
| 8 | P0-E Model switcher header | R1+R2+R4 | 1j |
| 9 | P0-G Unifier StatCard | R1+R4 | 1j |

**6 décisions ouvertes** (voir section "Notes à valider") avant de coder.

---

## Annexes

- Référence interne : `NURU_V9.md` § 11 Recommandations UI/UX
- Référence interne : `NURU_AUDIT_SYNTHESE.md` (lacunes L1-L7)
- Référence interne : `ROADMAP.md`
- Références externes :
  - `~/Downloads/AUDIT_UX_UI_NURU_V10.2.md` (R1 — 1676l)
  - `~/Downloads/AUDIT_UX_UI_NURU_V10.2_2.md` (R2 — 1030l)
  - `~/Downloads/AUDIT_UX_UI_NURU_V10.2_3.md` (R3 — 268l)
  - `~/Downloads/AUDIT_UX_UI_NURU_V10.2_4.md` (R4 — 1062l)
  - `~/Downloads/AUDIT_UX_UI_NURU_V10.2_5.md` (R5 — 231l)
