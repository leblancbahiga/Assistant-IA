"""
NURU V12 — Design Tokens (Z.ai spec exacte).

Palette DM-1 Deep Cyan, typographie, rayon, espacement.
Basé sur le design system board HTML de Z.ai.

Tokens extraits du mockup board :
  --bg-deep: #070A10
  --bg-card: #0D1117
  --bg-surface: #151B26
  Palette swatches : BG #0A0E17 / S1 #151B26 / S2 #1C2433 / ACC #00D4FF
"""

from dataclasses import dataclass
from typing import ClassVar


# ── Palette DM-1 Deep Cyan (Z.ai) ──────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Palette exacte du design system Z.ai."""

    # Fonds
    BG_DEEP: str = "#070A10"       # bg-deep — fond ultime
    BG_CARD: str = "#0D1117"       # bg-card — cartes, panneaux
    BG_SURFACE: str = "#151B26"    # bg-surface — surfaces interactives
    BG_SURFACE_2: str = "#1C2433"  # S2 — surface secondaire

    # Accent
    CYAN: str = "#00D4FF"          # Accent principal
    CYAN_DIM: str = "rgba(0, 212, 255, 0.6)"    # Dim
    CYAN_FAINT: str = "rgba(0, 212, 255, 0.08)" # Faint

    # Texte
    TEXT_PRIMARY: str = "#E8ECF1"  # TX — corps
    TEXT_SECONDARY: str = "#8B95A5"  # TX2 — caption
    TEXT_DIM: str = "#4A5568"      # text-dim — désactivé

    # États
    SUCCESS: str = "#00E599"       # accent-green
    WARNING: str = "#FFB800"       # accent-amber
    ERROR: str = "#FF4D6A"         # accent-rose

    # Overlay
    BG_OVERLAY: str = "rgba(7, 10, 16, 0.92)"  # VoiceOverlay

    # Bordures
    BORDER: str = "rgba(0, 212, 255, 0.12)"
    BORDER_STRONG: str = "rgba(0, 212, 255, 0.3)"

    # Palettes QPalette-swap
    DARK: ClassVar[dict] = {
        "bg": BG_DEEP,
        "card": BG_CARD,
        "surface": BG_SURFACE,
        "accent": CYAN,
        "text": TEXT_PRIMARY,
        "text_secondary": TEXT_SECONDARY,
        "border": BORDER,
    }

    LIGHT: ClassVar[dict] = {
        "bg": "#F4F6F9",
        "card": "#FFFFFF",
        "surface": "#FFFFFF",
        "accent": "#0099BB",
        "text": "#1A2332",
        "text_secondary": "#6B7A90",
        "border": "#D1D9E6",
    }


# ── Typographie Z.ai ───────────────────────────────────────────────

@dataclass(frozen=True)
class Typography:
    """Inter + JetBrains Mono — exactement la spec Z.ai."""

    FAMILY_BODY: str = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    FAMILY_CODE: str = "'JetBrains Mono', 'SF Mono', Monaco, monospace, sans-serif"

    # Tailles
    SIZE_BODY: int = 13          # px
    SIZE_CAPTION: int = 11       # px
    SIZE_TITLE: int = 18         # px
    SIZE_OVERLAY: int = 28       # px — prompt vocal
    SIZE_ORB_LABEL: int = 10     # px
    SIZE_BADGE: int = 10         # px — badges / tags
    SIZE_STATUS: int = 11        # px — pill statut

    # Poids
    WEIGHT_LIGHT: int = 300
    WEIGHT_NORMAL: int = 400
    WEIGHT_MEDIUM: int = 500
    WEIGHT_SEMIBOLD: int = 600
    WEIGHT_BOLD: int = 700
    WEIGHT_BLACK: int = 900


# ── Rayons Z.ai ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Radius:
    """Système de rayons hérité de macOS (Z.ai)."""

    SMALL: int = 4    # badges, petits composants
    MEDIUM: int = 8   # cartes, mockup cards
    LARGE: int = 12   # fenêtres, overlays


@dataclass(frozen=True)
class Spacing:
    """Espacements."""

    XS: int = 4
    SM: int = 8
    MD: int = 16
    LG: int = 24
    XL: int = 32


# ── Orb Z.ai ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrbSizes:
    """Tailles exactes du PresenceOrb selon Z.ai."""

    WINDOW: int = 120      # Dans l'ambiance
    OVERLAY: int = 200     # Dans le VoiceOverlay
    FLOATING: int = 80     # Dans le FloatingWidget


# ── Animations Z.ai ────────────────────────────────────────────────

@dataclass(frozen=True)
class AnimDuration:
    """Durées exactes de la spec Z.ai (ms)."""

    ORB_PULSE: int = 4000         # 4s — idle respiration
    ORB_HALO_SPIN: int = 3000     # 3s — halo réflexion
    ORB_PULSE_ACCEL: int = 1500   # 1.5s — respond
    OVERLAY_SHOW: int = 250       # 250ms — apparition overlay
    OVERLAY_HIDE: int = 250       # 250ms — disparition overlay
    FLOATING_FADE: int = 30000    # 30s — auto-dim floating


# ── Tailles composants Z.ai ────────────────────────────────────────

@dataclass(frozen=True)
class WidgetSizes:
    """Tailles exactes des composants Z.ai."""

    FLOATING_WIDTH: int = 220     # FloatingWidget (Z.ai: 220×160)
    FLOATING_HEIGHT: int = 160

    TOPBAR_HEIGHT: int = 56       # Top bar (Z.ai: 56px)
    STATUSBAR_HEIGHT: int = 24    # Status bar (Z.ai: 24px)

    OVERLAY_WIDTH_PCT: float = 0.6   # VoiceOverlay: 60% écran
    OVERLAY_HEIGHT_PCT: float = 0.4  # VoiceOverlay: 40% écran
