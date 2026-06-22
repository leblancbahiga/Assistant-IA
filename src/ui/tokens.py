"""
NURU V12 — Design Tokens (Z.ai spec exacte — doc concept).

Palette exacte du document NURU_V12_Concept_Interface.docx :
  bg-primary:    #0D1117
  bg-elevated:   #161B22
  accent-cyan:   #58D5E3
  accent-warm:   #E8A87C
  text-primary:  #E6EDF3

Typo : SF Pro (San Francisco) primaire, Inter fallback.
Rayons : 4 / 12 / 16 px (macOS natif).
"""

from dataclasses import dataclass
from typing import ClassVar


# ── Palette Z.ai (doc concept) ────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Palette exacte du document Z.ai V12."""

    # Fonds
    BG_DEEP: str = "#0D1117"       # bg-primary — fond principal
    BG_ELEVATED: str = "#161B22"   # bg-elevated — cartes, surfaces surélevées
    BG_OVERLAY: str = "rgba(13,17,23,0.92)"  # overlay vocal semi-transparent

    # Accent
    CYAN: str = "#58D5E3"          # accent-cyan — indicateurs d'état, liens, focus
    CYAN_GLOW: str = "rgba(88,213,227,0.15)"  # halo / glow animation
    WARM: str = "#E8A87C"          # accent-warm — notifications proactives

    # Texte
    TEXT_PRIMARY: str = "#E6EDF3"  # text-primary
    TEXT_SECONDARY: str = "#8B949E"  # text-secondary — légendes, captions
    TEXT_MUTED: str = "#484F58"    # text-muted — placeholders, désactivé

    # Bordures
    BORDER: str = "#21262D"        # border-subtle — séparateurs discrets

    # États
    SUCCESS: str = "#3FB950"       # success
    ERROR: str = "#F85149"         # danger — F85149 dans le doc

    # Overlay overlay
    BG_OVERLAY_WARM: str = "rgba(232,168,124,0.12)"  # warm toast BG


    # Palettes swap
    DARK: ClassVar[dict] = {
        "bg": BG_DEEP,
        "card": BG_ELEVATED,
        "surface": BG_ELEVATED,
        "accent": CYAN,
        "text": TEXT_PRIMARY,
        "text_secondary": TEXT_SECONDARY,
        "border": BORDER,
    }

    LIGHT: ClassVar[dict] = {
        "bg": "#F4F6F9",
        "card": "#FFFFFF",
        "surface": "#FFFFFF",
        "accent": "#3A9DB5",
        "text": "#1A2332",
        "text_secondary": "#6B7A90",
        "border": "#D1D9E6",
    }


# ── Typographie Z.ai : SF Pro primaire, Inter fallback ────────────

@dataclass(frozen=True)
class Typography:
    """SF Pro (San Francisco) primaire, Inter fallback — Z.ai exact."""

    FAMILY_BODY: str = "'SF Pro Display', 'SF Pro Text', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    FAMILY_CODE: str = "'JetBrains Mono', 'SF Mono', Monaco, monospace, sans-serif"

    # Poids (Z.ai §99-138)
    WEIGHT_LIGHT: int = 300       # Overlay prompt
    WEIGHT_REGULAR: int = 400     # Body, Caption, Code
    WEIGHT_MEDIUM: int = 500      # Usage intermédiaire
    WEIGHT_SEMIBOLD: int = 600    # Titre assistant, H2
    WEIGHT_BOLD: int = 700        # H1

    # Tailles
    SIZE_ORB_LABEL: int = 24     # pt — titre assistant (SF Pro Display 600)
    SIZE_HEADING_1: int = 18     # pt — H1
    SIZE_HEADING_2: int = 15     # pt — H2
    SIZE_BODY: int = 13          # pt — messages, réponses
    SIZE_CAPTION: int = 11       # pt — métadonnées, timestamps
    SIZE_CODE: int = 12          # pt — JetBrains Mono
    SIZE_OVERLAY: int = 28       # pt — prompt vocal (SF Pro Display 300)


# ── Rayons Z.ai (macOS natif) ─────────────────────────────────────

@dataclass(frozen=True)
class Radius:
    """Système de rayons Z.ai : 4 / 12 / 16 px."""

    SMALL: int = 4     # badges, petits indicateurs
    MEDIUM: int = 12   # cartes, conteneurs modaux
    LARGE: int = 16    # overlay principal


# ── Espacements (base 4px) ───────────────────────────────────────

@dataclass(frozen=True)
class Spacing:
    """Système base 4px."""

    XS: int = 4
    SM: int = 8
    MD: int = 12
    LG: int = 16
    XL: int = 20
    XXL: int = 24
    XXXL: int = 32
    HUGE: int = 48


# ── Orb Z.ai ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrbSizes:
    """Tailles exactes NuruPresenceOrb (Z.ai doc)."""

    WINDOW: int = 120      # fenêtre principale
    OVERLAY: int = 200     # VoiceOverlay
    FLOATING: int = 80     # FloatingWidget


# ── Animations Z.ai (doc) ────────────────────────────────────────

@dataclass(frozen=True)
class AnimDuration:
    """Durées exactes du document Z.ai."""

    ORB_PULSE: int = 4000         # 4s — respiration idle
    ORB_HALO_SPIN: int = 8000     # 8s — halo réflexion (doc: spin 8s)
    ORB_PULSE_ACCEL: int = 1500   # 1.5s — respond
    STATE_TRANSITION: int = 300   # 300ms — transitions entre états (doc)
    OVERLAY_SHOW: int = 250       # 250ms — apparition overlay (doc: scale+opacity 250ms)
    OVERLAY_HIDE: int = 250       # 250ms — disparition
    OVERLAY_TIMEOUT: int = 8000   # 8s — timeout vocal (doc)
    SOUND_WAVE_DURATION: int = 2000  # 2s — onde sonore (doc: 60→120px)
    SOUND_WAVE_OFFSET: int = 600  # 0.6s — décalage entre cercles
    TOAST_SHOW: int = 300         # 300ms — apparition toast
    TOAST_VISIBLE: int = 4000     # 4s — visible
    TOAST_HIDE: int = 200         # 200ms — disparition
    CHAT_BUBBLE: int = 200        # 200ms — apparition bulle
    FLOATING_FADE: int = 30000    # 30s — auto-dim floating widget


# ── Tailles fenêtres Z.ai ────────────────────────────────────────

@dataclass(frozen=True)
class WindowSizes:
    """Tailles exactes des fenêtres (doc Z.ai)."""

    WINDOW_WIDTH: int = 720       # NuruWindow (doc: resize(720, 860))
    WINDOW_HEIGHT: int = 860
    WINDOW_MIN_WIDTH: int = 480   # min size
    WINDOW_MIN_HEIGHT: int = 600

    FLOATING_SIZE: int = 160     # FloatingWidget (doc: 160×160)

    OVERLAY_WIDTH_PCT: float = 0.6   # VoiceOverlay: 60% écran
    OVERLAY_HEIGHT_PCT: float = 0.4  # VoiceOverlay: 40% écran
