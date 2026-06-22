"""
NURU V12 — Design Tokens (Design System DM-1 "Deep Cyan").

Palette extraite du mockup board V12 (nuru_v12_mockup_board.html) :
  bg-deep:       #0A0E17   — fond principal, dot grid
  bg-surface1:   #151B26   — cartes, surfaces surélevées
  bg-surface2:   #1C2433   — surface secondaire
  accent-cyan:   #00D4FF   — orb, glow, liens, focus
  accent-green:  #00E599   — état idle, succès
  accent-amber:  #FFB800   — état thinking, notifications
  accent-rose:   #FF4D6A   — état erreur
  text-primary:  #E8ECF1   — texte principal
  text-secondary:#8B95A5   — légendes, captions
  text-dim:      #4A5568   — placeholders, désactivé
  border:        rgba(0, 212, 255, 0.12) — séparateurs discrets
  border-strong: rgba(0, 212, 255, 0.30) — focus, hover

Typo : Inter primaire, JetBrains Mono pour le code.
Rayons : 8 / 12 px (macOS natif, M1 friendly).
"""

from dataclasses import dataclass
from typing import ClassVar


# ── Palette DM-1 "Deep Cyan" (mockup board V12) ─────────────────

@dataclass(frozen=True)
class Color:
    """Design System DM-1 — NURU V12 mockup board exact."""

    # Fonds
    BG_DEEP: str = "#0A0E17"       # fond principal — orb plein écran, dot grid
    BG_SURFACE1: str = "#151B26"   # cartes, surfaces surélevées (anciennement BG_ELEVATED)
    BG_ELEVATED: str = "#151B26"   # alias de compatibilité
    BG_SURFACE2: str = "#1C2433"   # surface secondaire
    BG_OVERLAY: str = "rgba(10, 14, 23, 0.92)"  # overlay vocal semi-transparent

    # Accent — DM-1
    CYAN: str = "#00D4FF"          # accent principal — orb, glow, liens, focus
    CYAN_GLOW: str = "rgba(0, 212, 255, 0.15)"   # halo / glow animation
    CYAN_FAINT: str = "rgba(0, 212, 255, 0.08)"  # fond subtiles
    GREEN: str = "#00E599"         # état idle, succès — Listening
    AMBER: str = "#FFB800"         # état thinking — warm notifications
    ROSE: str = "#FF4D6A"          # état error
    WARM: str = "#FFB800"         # alias compatibilité (anciennement accent-warm)

    # Texte
    TEXT_PRIMARY: str = "#E8ECF1"  # texte principal
    TEXT_SECONDARY: str = "#8B95A5"  # légendes, captions
    TEXT_MUTED: str = "#4A5568"    # placeholders, désactivé

    # Bordures
    BORDER: str = "rgba(0, 212, 255, 0.12)"       # séparateurs discrets
    BORDER_STRONG: str = "rgba(0, 212, 255, 0.30)"  # focus, hover

    # Alias hérités (compatibilité)
    BG_CARD: str = "#151B26"

    # États
    SUCCESS: str = "#00E599"
    ERROR: str = "#FF4D6A"

    # Overlay warm
    BG_OVERLAY_WARM: str = "rgba(255, 184, 0, 0.12)"

    # Palettes swap
    DARK: ClassVar[dict] = {
        "bg": BG_DEEP,
        "card": BG_SURFACE1,
        "surface": BG_SURFACE1,
        "surface2": BG_SURFACE2,
        "accent": CYAN,
        "text": TEXT_PRIMARY,
        "text_secondary": TEXT_SECONDARY,
        "text_dim": TEXT_MUTED,
        "border": BORDER,
        "green": GREEN,
        "amber": AMBER,
        "rose": ROSE,
    }

    LIGHT: ClassVar[dict] = {
        "bg": "#F0F4F8",
        "card": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface2": "#E8ECF1",
        "accent": "#0099BB",
        "text": "#1A2332",
        "text_secondary": "#6B7A90",
        "text_dim": "#A0AAB8",
        "border": "#D1D9E6",
        "green": "#00B377",
        "amber": "#CC9300",
        "rose": "#D43D57",
    }


# ── Typographie DM-1 : Inter primaire, JetBrains Mono code ─────────

@dataclass(frozen=True)
class Typography:
    """Inter primaire, JetBrains Mono pour le code — DM-1 exact."""

    FAMILY_BODY: str = "'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif"
    FAMILY_CODE: str = "'JetBrains Mono', 'SF Mono', Monaco, monospace, sans-serif"

    # Poids
    WEIGHT_LIGHT: int = 300       # Overlay prompt, transcript
    WEIGHT_REGULAR: int = 400     # Body, Caption, Code
    WEIGHT_MEDIUM: int = 500      # Usage intermédiaire
    WEIGHT_SEMIBOLD: int = 600    # Titre assistant, H2
    WEIGHT_BOLD: int = 700        # H1, NURU label

    # Tailles
    SIZE_ORB_LABEL: int = 24     # pt — titre assistant
    SIZE_HEADING_1: int = 18     # pt — H1
    SIZE_HEADING_2: int = 15     # pt — H2
    SIZE_BODY: int = 13          # pt — messages, réponses
    SIZE_CAPTION: int = 11       # pt — métadonnées, timestamps
    SIZE_CODE: int = 12          # pt — JetBrains Mono
    SIZE_OVERLAY: int = 28       # pt — prompt vocal


# ── Rayons DM-1 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Radius:
    """Système de rayons DM-1 — macOS natif, M1 friendly."""

    SMALL: int = 4     # badges, petits indicateurs
    MEDIUM: int = 8    # cartes, conteneurs
    LARGE: int = 12   # overlay, floating widget
    WIDGET: int = 12   # floating widget coins arrondis


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


# ── Orb DM-1 ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrbSizes:
    """Tailles exactes NuruPresenceOrb (DM-1)."""

    WINDOW: int = 120      # fenêtre principale
    OVERLAY: int = 200     # VoiceOverlay
    FLOATING: int = 80     # FloatingWidget mini-orb


# ── Animations DM-1 ─────────────────────────────────────────────

@dataclass(frozen=True)
class AnimDuration:
    """Durées exactes DM-1."""

    ORB_PULSE: int = 4000         # 4s — respiration idle
    ORB_HALO_SPIN: int = 8000     # 8s — halo réflexion
    ORB_PULSE_ACCEL: int = 1500   # 1.5s — respond
    STATE_TRANSITION: int = 300   # 300ms — transitions
    OVERLAY_SHOW: int = 250       # 250ms — apparition overlay
    OVERLAY_HIDE: int = 250       # 250ms — disparition
    OVERLAY_TIMEOUT: int = 8000   # 8s — timeout vocal
    SOUND_WAVE_DURATION: int = 2000  # 2s — onde sonore
    SOUND_WAVE_OFFSET: int = 600  # 0.6s — décalage entre cercles
    TOAST_SHOW: int = 300         # 300ms
    TOAST_VISIBLE: int = 4000     # 4s
    TOAST_HIDE: int = 200         # 200ms
    CHAT_BUBBLE: int = 200        # 200ms — apparition bulle
    FLOATING_FADE: int = 30000    # 30s — auto-dim floating widget


# ── Tailles fenêtres DM-1 ────────────────────────────────────────

@dataclass(frozen=True)
class WindowSizes:
    """Tailles exactes des fenêtres (DM-1)."""

    WINDOW_WIDTH: int = 720
    WINDOW_HEIGHT: int = 860
    WINDOW_MIN_WIDTH: int = 480
    WINDOW_MIN_HEIGHT: int = 600

    FLOATING_WIDTH: int = 260    # FloatingWidget — DM-1: 260×180
    FLOATING_HEIGHT: int = 180   # (doc: 220×160 + padding)
    FLOATING_SIZE: int = 260     # alias (carré pour compatibilité)

    OVERLAY_WIDTH_PCT: float = 0.6
    OVERLAY_HEIGHT_PCT: float = 0.4
