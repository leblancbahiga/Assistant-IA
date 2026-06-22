"""
NURU V12 — Design Tokens (Z.ai spec).

Palette, typographie, rayon, espacement — single source of truth
pour toute l'interface PySide6.

Basé sur le design system Deep Cyan de Z.ai (NURU_V9.md §2070-2260).
"""

from dataclasses import dataclass, field
from typing import ClassVar


# ── Palette ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Couleurs NURU V12 — Design System Deep Cyan (Z.ai)."""

    # Fond
    BG_DEEP: str = "#0A0E17"       # Fond principal
    BG_SURFACE: str = "#151B26"    # Surfaces (cartes, inputs)
    BG_OVERLAY: str = "rgba(13,17,23,0.92)"  # VoiceOverlay

    # Accent
    CYAN: str = "#00D4FF"          # Accent principal
    CYAN_LIGHT: str = "#66E5FF"    # Hover / highlight
    CYAN_DIM: str = "#0099BB"      # Light mode accent

    # Texte
    TEXT_PRIMARY: str = "#E8ECF1"  # Corps
    TEXT_SECONDARY: str = "#8B95A5"  # Caption / secondaire
    TEXT_DISABLED: str = "#4A5568"  # Désactivé

    # États
    ERROR: str = "#FF4D6A"         # Erreur / alerte
    WARNING: str = "#FFB84D"       # Attention
    SUCCESS: str = "#39FF14"       # Succès

    # Bordures / séparateurs
    BORDER: str = "#2A3344"
    BORDER_FOCUS: str = "#00D4FF"

    # Palettes
    DARK: ClassVar[dict] = field(default=None)  # type: ignore
    LIGHT: ClassVar[dict] = field(default=None)  # type: ignore


# Palettes QPalette-swap
Color.DARK = {
    "bg": Color.BG_DEEP,
    "surface": Color.BG_SURFACE,
    "accent": Color.CYAN,
    "text": Color.TEXT_PRIMARY,
    "text_secondary": Color.TEXT_SECONDARY,
    "border": Color.BORDER,
}

Color.LIGHT = {
    "bg": "#F4F6F9",
    "surface": "#FFFFFF",
    "accent": Color.CYAN_DIM,
    "text": "#1A2332",
    "text_secondary": "#6B7A90",
    "border": "#D1D9E6",
}


# ── Typographie ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Typography:
    """Polices et tailles NURU V12."""

    FAMILY_BODY: str = "Inter, -apple-system, sans-serif"
    FAMILY_CODE: str = "JetBrains Mono, SF Mono, Monaco, monospace"

    SIZE_BODY: int = 13          # px — texte principal
    SIZE_CAPTION: int = 11       # px — sous-titres
    SIZE_TITLE: int = 18         # px — titres
    SIZE_OVERLAY: int = 28       # px — prompt vocal
    SIZE_ORB_LABEL: int = 10     # px — label sous l'Orb

    WEIGHT_NORMAL: int = 400
    WEIGHT_MEDIUM: int = 500
    WEIGHT_BOLD: int = 700


# ── Rayons & espacements ──────────────────────────────────────────────

@dataclass(frozen=True)
class Radius:
    """Coins arrondis — système Z.ai (4/12/16 px)."""

    SMALL: int = 4
    MEDIUM: int = 12
    LARGE: int = 16
    PILL: int = 999  # cercles/badges


@dataclass(frozen=True)
class Spacing:
    """Espacements verticaux/horizontaux — design system."""

    XS: int = 4
    SM: int = 8
    MD: int = 16
    LG: int = 24
    XL: int = 32


# ── Orb ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrbSizes:
    """Tailles du PresenceOrb selon le contexte (Z.ai)."""

    WINDOW: int = 120       # Dans la fenêtre principale
    OVERLAY: int = 200      # Dans le VoiceOverlay
    FLOATING: int = 80      # Dans le FloatingWidget


# ── Animations ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AnimDuration:
    """Durées d'animation (ms) — Z.ai spec."""

    ORB_PULSE: int = 4000         # 4s — idle respiration
    ORB_HALO_SPIN: int = 3000     # 3s — halo réflexion
    ORB_PULSE_ACCEL: int = 1500   # 1.5s — respond pulse accéléré
    OVERLAY_SHOW: int = 250       # 250ms — apparition overlay
    OVERLAY_HIDE: int = 250       # 250ms — disparition overlay
    TOAST_VISIBLE: int = 4000     # 4s — visibilité toast
    TOAST_SLIDE: int = 300        # 300ms — glissement toast
    FLOATING_FADE: int = 30000    # 30s — avant auto-dim floating
