# Question pour Z.ai — Refonte Interface Visuelle NURU V12

---

**Contexte :** NURU est un assistant personnel RAG+agentique sur Mac M1 8 Go (Python/PySide6). Après 6 audits experts, nous lançons le plan V12 : contrôle environnement, voix conversationnelle, vision écran, proactivité, MCP.

**Le vrai problème :** L'interface actuelle est un dashboard technique 3 colonnes qui ressemble à un cockpit d'avion. L'utilisateur la trouve moche et inadaptée à un assistant personnel moderne.

**Objectif :** Une refonte complète de l'interface PySide6 pour qu'elle incarne un **assistant personnel vocal et visuel** digne de JARVIS — pas un cockpit, pas un chat glorifié, mais une présence numérique élégante et vivante à l'écran.

**Contraintes :**
- M1 8 Go RAM — certains effets visuels sont possibles, pas de 3D lourde temps réel
- PySide6/Qt — pas de React, pas de web
- Architecture EventBus existante
- L'interface doit supporter 3 modes : chat texte, conversation vocale (overlay), et exécution d'actions

**Peux-tu nous proposer un concept d'interface V12 qui :**

1. **Change radicalement de paradigme** — fini le cockpit technique. On veut une interface qui ressemble à un assistant personnel : épurée, élégante, avec une identité visuelle forte. Inspirations : JARVIS (HUD transparent, informations contextuelles), Her (minimalisme chaleureux), ou un mix des deux.

2. **Inclut des éléments visuels animés** qui donnent vie à l'assistant : onde sonore pendant l'écoute, halo lumineux pendant la réflexion, notifications fluides, micro-interactions qui créent une sensation de « présence ».

3. **S'adapte au mode vocal** — quand l'utilisateur dit « Hey NURU », l'interface doit changer : overlay discret par-dessus les autres apps (type Siri/Spotlight), feedback visuel de l'écoute, indicateur que l'assistant écoute/parle/réfléchit.

4. **Reste proche du système** — intégration native macOS : menu bar widget, notification center, raccourcis clavier, possiblement un Always-On-Top widget flottant minimal.

5. **Donne des directions concrètes** : palette de couleurs, typographie, layout des composants, quels composants créer, lesquels supprimer de l'interface actuelle (sidebar complète ? panneau de métriques ?), comment organiser l'information sans submerger l'utilisateur.
