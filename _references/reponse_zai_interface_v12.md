# Réponse Z.ai — Interface V12 (v2)

**Date** : 2026-06-20 | **Source** : Échange via Leblanc

Questions posées et réponses complètes de Z.ai sur l'implémentation de l'interface NURU V12.

---

## Q1 — Thème clair

**Non exclusif, mais dégradé.** NURU V12 reste nocturne par défaut (son identité), mais un mode clair est envisageable comme **profil basculable**, pas comme un thème de même rang. L'Orb et les effets de glow perdent 80% de leur impact sur fond clair.

**Approche : inversion par paliers, pas de palette parallèle**

| Élément | Dark (défaut) | Light (optionnel) |
|---------|--------------|-------------------|
| Background | `#0A0E17` | `#F4F6F9` |
| Surface 1 | `#151B26` | `#FFFFFF` |
| Accent | `#00D4FF` | `#0099BB` (cyan assombri de ~15%) |
| Text | `#E8ECF1` | `#1A2332` |
| Orb glow | Radial cyan 40% opacité | Radial cyan 12% opacité |

**Key insight** : ne pas créer un "thème clair" séparé, mais une **transformation algébrique** sur les tokens existants (inversion de lightness + réduction de l'opacité des effets de glow). En PySide6, ça se fait via un `QPalette` swap + un `opacity_multiplier` property sur l'Orb — pas de duplication.

Activation : `Cmd+Shift+L` ou auto-détection macOS (`NSAppearanceObserver`).

---

## Q2 — Mode action

Le `ProactiveToast` seul est **insuffisant**. Le toast est éphémère (3-5s), alors qu'une action peut durer 30s+. L'utilisateur perd le contexte visuel.

**Recommandation : ajouter un état `acting` à l'Orb**

| État | Signal EventBus | Visuel Orb | Durée |
|------|----------------|-----------|-------|
| Idle | — | Pulsing doux, 1 cycle/4s | Permanent |
| Listening | `voice.wake_detected` | Glow intensifié + rings | Jusqu'à transcript |
| Thinking | `voice.thinking_start` | Rotation lente (1 tr/3s) + couleur blanchie | Jusqu'à response |
| **Acting** | **`action.started`** | **Orb scale 0.85 + anneau progression (arc partiel, clockwise)** | Jusqu'à `action.completed` |
| Responding | `voice.response_start` | Pulsing accéléré (1 cycle/1.5s) | Jusqu'à session_end |

L'état **Acting** : l'anneau de progression (`QPainter::drawArc`) donne un feedback continu sans être intrusif. L'Orb reste en arrière-plan, mais l'œil peripheral capte le mouvement.

Pour les actions longues (>10s), un `ProactiveToast` **complète** l'Orb (ex: "Modification de config.yaml… 67%") mais ne le **remplace** pas. **Règle : l'Orb = toujours présent, le toast = toujours optionnel.**

```python
class ActionState(QObject):
    progress = Signal(float)  # 0.0 → 1.0

    def on_action_started(self, action_name):
        self.orb.enter_state("acting")
        self.action_label.setText(action_name)

    def on_progress_update(self, pct):
        self.progress_arc_angle = int(360 * pct)

    def on_action_completed(self, result):
        self.orb.enter_state("idle")
        self.toast.show(f"{result}", duration=3000)
```

---

## Q3 — Responsive

**Redimensionnement fluide, pas de paliers.** L'Orb est intrinsèquement scalable (QPainter, pas du pixel art).

**Principe : l'Orb occupe toujours `min(width, height) * 0.25`**

```
1920×1080 → Orb = 270px diameter
1440×900  → Orb = 225px diameter
1280×800  → Orb = 200px diameter
1024×600  → Orb = 150px diameter
```

| Composant | 1280×800 |
|-----------|----------|
| Presence Orb | 200px (vs 270px) — toujours lisible |
| FloatingWidget | 180×140px (vs 220×160) — même layout |
| VoiceOverlay | Transcription 18px → 16px |
| WaveformRings | Rayon réduit proportionnellement |

**Ce qui ne change pas :** menu bar icon (22px), raccourcis clavier, tray menu.

```python
def resizeEvent(self, event):
    size = min(self.width(), self.height())
    self.orb_radius = size * 0.125  # diamètre = 25%
    self.orb_center = QPointF(self.width()/2, self.height()/2)
    self.update()
```

Pour le floating widget, ombre retirée sous 1440px de large (économie GPU M1 8GB).

---

## Q4 — Parallélisme roadmap

**Fort potentiel de chevauchement.** Les phases ne sont pas bloquantes séquentiellement :

```
Phase 1: Socle technique      ────→  Phase 2: Animations + Voice
  ├─ NuruWindow (frameless)           ├─ NuruPresenceOrb
  ├─ EventBus backbone                ├─ VoiceOverlay
  └─ QSystemTrayIcon                  └─ WaveformRings
                                            │
Phase 1.5: Floating Widget ──────────┘ (peut démarrer dès que
  ├─ Widget layout                     NuruWindow existe)
  └─ Tray menu                         // Pas dépendant de
                                        // l'Orb pour exister
```

| Sprint | Phase 1 | Phase 1.5 | Phase 2 |
|--------|---------|-----------|---------|
| Sem 1-2 | NuruWindow + EventBus | — | — |
| Sem 2-3 | QSystemTrayIcon | FloatingWidget layout | NuruPresenceOrb (QPainter) |
| Sem 3-4 | Menu contextuel | Widget→tray liaison | VoiceOverlay + WaveformRings |
| Sem 5 | Tests intégration | Dark/Light toggle | États Orb |

**Key insight :** le FloatingWidget ne dépend **que** de `NuruWindow` (window flags) et de `QSystemTrayIcon` (toggle). Aucune dépendance sur l'Orb ou les animations.

**Risque du parallélisme :** si le widget est fonctionnel avant l'Orb, il affiche un placeholder (cercle gris statique). Acceptable — le widget est d'abord utilitaire (raccourcis, dernière conversation), l'Orb est la cerise visuelle.
