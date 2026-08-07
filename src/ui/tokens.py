"""
NURU V15 — Design System "NEON COGNITIVE"
——————————————————————————————
Palette néon cybernétique + verre morphique pour système cognitif avancé.

Philosophie visuelle :
  - Fond espace profond (#05080F) avec champs de particules
  - Panneaux en verre morphique (glass-morphism) avec reflets
  - Cyan néon (#00F0FF) comme primaire — énergie, conscience
  - Violet néon (#7C3AED) comme secondaire — profondeur, cognition
  - Vert cyber (#00FFAA) — succès, présence
  - Ambre (#FFB800) — réflexion, alerte
  - Rose néon (#FF3366) — erreur, signal

Contraintes M1 8 Go :
  - Pas de QGraphicsBlurEffect (trop coûteux) — simulé par gradients
  - Particules limitées (~50 max)
  - Single QTimer pour toutes les animations
"""

from dataclasses import dataclass
from typing import ClassVar


# ── Palette NEON COGNITIVE ─────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """NEON COGNITIVE — née du cyan, élevée par le violet."""

    # Fonds
    BG_DEEP: str = "#05080F"       # espace profond — fond principal
    BG_SURFACE1: str = "rgba(12, 20, 40, 0.72)"  # verre morphique
    BG_ELEVATED: str = "rgba(12, 20, 40, 0.72)"  # alias compatibilité
    BG_SURFACE2: str = "rgba(18, 28, 52, 0.65)"  # verre secondaire
    BG_SURFACE3: str = "rgba(24, 36, 64, 0.60)"  # verre troisième plan
    BG_OVERLAY: str = "rgba(5, 8, 15, 0.88)"     # overlay vocal

    # Accents néon
    CYAN: str = "#00F0FF"           # primaire — néon cyan
    CYAN_GLOW: str = "rgba(0, 240, 255, 0.15)"   # halo doux
    CYAN_GLOW_STRONG: str = "rgba(0, 240, 255, 0.30)"  # halo fort
    CYAN_FAINT: str = "rgba(0, 240, 255, 0.06)"  # fond subtil
    CYAN_SHADOW: str = "rgba(0, 240, 255, 0.4)"  # ombre néon

    VIOLET: str = "#7C3AED"         # secondaire — violet néon
    VIOLET_GLOW: str = "rgba(124, 58, 237, 0.20)"
    VIOLET_FAINT: str = "rgba(124, 58, 237, 0.08)"

    # États
    GREEN: str = "#00FFAA"          # succès, présence idle
    GREEN_GLOW: str = "rgba(0, 255, 170, 0.15)"
    AMBER: str = "#FFB800"          # réflexion, alerte
    AMBER_GLOW: str = "rgba(255, 184, 0, 0.15)"
    ROSE: str = "#FF3366"           # erreur, signal fort
    ROSE_GLOW: str = "rgba(255, 51, 102, 0.15)"

    # Texte
    TEXT_PRIMARY: str = "#E8F0FF"   # blanc légèrement bleuté
    TEXT_SECONDARY: str = "#8BA0C8"  # bleu-gris clair
    TEXT_MUTED: str = "rgba(139, 160, 200, 0.45)"  # discret

    # Bordures verre morphique
    BORDER: str = "rgba(0, 240, 255, 0.08)"        # séparation subtile
    BORDER_MEDIUM: str = "rgba(0, 240, 255, 0.15)" # hover
    BORDER_STRONG: str = "rgba(0, 240, 255, 0.35)" # focus, actif
    BORDER_VIOLET: str = "rgba(124, 58, 237, 0.20)" # violette

    # Reflets verre (highlight interne)
    GLASS_HIGHLIGHT: str = "rgba(255, 255, 255, 0.04)"
    GLASS_HIGHLIGHT_STRONG: str = "rgba(255, 255, 255, 0.08)"

    # Aliases hérités
    BG_CARD: str = BG_SURFACE1
    SUCCESS: str = GREEN
    ERROR: str = ROSE
    WARM: str = AMBER
    BG_OVERLAY_WARM: str = "rgba(255, 184, 0, 0.10)"

    # Palettes swap pour préférence clair/sombre
    DARK: ClassVar[dict] = {
        "bg": BG_DEEP,
        "card": BG_SURFACE1,
        "surface": BG_SURFACE1,
        "surface2": BG_SURFACE2,
        "accent": CYAN,
        "violet": VIOLET,
        "text": TEXT_PRIMARY,
        "text_secondary": TEXT_SECONDARY,
        "text_dim": TEXT_MUTED,
        "border": BORDER,
        "green": GREEN,
        "amber": AMBER,
        "rose": ROSE,
    }

    LIGHT: ClassVar[dict] = {
        "bg": "#E8F0FF",
        "card": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface2": "#D6E4F0",
        "accent": "#0088CC",
        "violet": "#6D28D9",
        "text": "#0A1628",
        "text_secondary": "#4A6580",
        "text_dim": "#8BA0C0",
        "border": "#C0D4E8",
        "green": "#008866",
        "amber": "#996600",
        "rose": "#CC2255",
    }


# ── Typographie ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Typography:
    """SF Pro + JetBrains Mono — lisibilité maximale sur fond sombre."""

    FAMILY_BODY: str = "'SF Pro Display', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    FAMILY_CODE: str = "'SF Mono', 'JetBrains Mono', 'Fira Code', monospace"
    FAMILY_DISPLAY: str = "'SF Pro Display', 'Inter', sans-serif"

    # Poids
    WEIGHT_THIN: int = 200
    WEIGHT_LIGHT: int = 300
    WEIGHT_REGULAR: int = 400
    WEIGHT_MEDIUM: int = 500
    WEIGHT_SEMIBOLD: int = 600
    WEIGHT_BOLD: int = 700

    # Tailles (pt)
    SIZE_ORB_LABEL: int = 22
    SIZE_HEADING_1: int = 17
    SIZE_HEADING_2: int = 14
    SIZE_BODY: int = 13
    SIZE_CAPTION: int = 11
    SIZE_CODE: int = 11
    SIZE_OVERLAY: int = 26
    SIZE_SMALL: int = 10


# ── Rayons ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Radius:
    """Rayons harmonieux — glass-morphism friendly."""

    XS: int = 4
    SMALL: int = 6  # alias SM (agents_page, tools_page)
    SM: int = 6
    MEDIUM: int = 10
    LARGE: int = 14
    WIDGET: int = 16
    PILL: int = 999  # arrondi maximal


# ── Espacements (base 4px) ────────────────────────────────────────

@dataclass(frozen=True)
class Spacing:
    XS: int = 4
    SM: int = 8
    MD: int = 12
    LG: int = 16
    XL: int = 20
    XXL: int = 24
    XXXL: int = 32
    HUGE: int = 48
    MASSIVE: int = 64


# ── Orb ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrbSizes:
    WINDOW: int = 130       # fenêtre principale — plus large
    OVERLAY: int = 200      # VoiceOverlay
    FLOATING: int = 80      # FloatingWidget mini-orb
    AURA_MAX: int = 50      # particules max autour de l'orb


# ── Animations ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class AnimDuration:
    ORB_PULSE: int = 3000          # 3s — respiration
    ORB_HALO_SPIN: int = 6000      # 6s — rotation halo
    ORB_PARTICLE_SPIN: int = 8000  # 8s — particules orbitales
    STATE_TRANSITION: int = 400    # 400ms — transitions douces
    OVERLAY_SHOW: int = 300
    OVERLAY_HIDE: int = 250
    OVERLAY_TIMEOUT: int = 8000
    SOUND_WAVE_DURATION: int = 2000
    TOAST_SHOW: int = 300
    TOAST_VISIBLE: int = 4000
    TOAST_HIDE: int = 200
    CHAT_BUBBLE: int = 250
    FLOATING_FADE: int = 30000
    GLOW_SHIFT: int = 4000         # 4s — shift de couleur du glow


# ── Fenêtres ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class WindowSizes:
    WINDOW_WIDTH: int = 760
    WINDOW_HEIGHT: int = 900
    WINDOW_MIN_WIDTH: int = 480
    WINDOW_MIN_HEIGHT: int = 600

    FLOATING_WIDTH: int = 280
    FLOATING_HEIGHT: int = 200
    FLOATING_SIZE: int = 280

    OVERLAY_WIDTH_PCT: float = 0.6
    OVERLAY_HEIGHT_PCT: float = 0.4

    SIDEBAR_WIDTH: int = 200
    SIDEBAR_COLLAPSED: int = 52
