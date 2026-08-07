"""
NURU V16 — QSS Builder.
Génère les feuilles de style depuis tokens.py.
Un seul point de vérité : un changement dans tokens.py → tout l'UI reflète.
"""

from __future__ import annotations

from src.ui.tokens import Color, Spacing, Radius, Typography


def build_qss(dark: bool = True) -> str:
    """Génère le QSS global pour le thème dark (ou light)."""
    pal = Color.DARK if dark else Color.LIGHT

    return f"""
    /* ── NURU V16 — QSS généré depuis tokens.py ── */

    QMainWindow {{
        background-color: {pal["bg"]};
        color: {pal["text"]};
        font-family: {Typography.FAMILY_BODY};
        font-size: {Typography.SIZE_BODY}pt;
    }}

    QWidget {{
        background-color: transparent;
        color: {pal["text"]};
        font-family: {Typography.FAMILY_BODY};
    }}

    /* ── Sidebar ── */
    #Sidebar {{
        background-color: rgba(8, 12, 22, 0.85);
        border-right: 1px solid {pal["border"]};
    }}

    #SidebarItem {{
        background-color: transparent;
        color: {pal["text_secondary"]};
        border: none;
        border-radius: {Radius.MEDIUM}px;
        padding: 0 {Spacing.MD}px;
        text-align: left;
        font-size: {Typography.SIZE_BODY}pt;
        font-family: {Typography.FAMILY_BODY};
    }}

    #SidebarItem:hover {{
        background-color: {Color.CYAN_FAINT};
        color: {pal["text"]};
    }}

    #SidebarItem:checked {{
        background-color: {Color.CYAN_GLOW};
        color: {Color.CYAN};
        border-left: 2px solid {Color.CYAN};
    }}

    /* QToolButton dans la sidebar */
    QToolButton#SidebarItem {{
        background-color: transparent;
        color: {pal["text_secondary"]};
        border: none;
        border-radius: {Radius.MEDIUM}px;
        padding: 0 {Spacing.MD}px;
        text-align: left;
        font-size: {Typography.SIZE_BODY}pt;
        font-family: {Typography.FAMILY_BODY};
    }}

    QToolButton#SidebarItem:hover {{
        background-color: {Color.CYAN_FAINT};
        color: {pal["text"]};
    }}

    QToolButton#SidebarItem:checked {{
        background-color: {Color.CYAN_GLOW};
        color: {Color.CYAN};
        border-left: 2px solid {Color.CYAN};
    }}

    /* ── StatusBar ── */
    QStatusBar {{
        background-color: {pal["bg"]};
        border-top: 1px solid {pal["border"]};
        color: {pal["text_muted"] if "text_muted" in pal else pal["text_secondary"]};
        font-size: {Typography.SIZE_CAPTION}pt;
        padding: 0 {Spacing.SM}px;
    }}

    /* ── Right Inspector ── */
    #RightInspectorPanel {{
        background-color: rgba(10, 16, 30, 0.80);
        border-left: 1px solid {pal["border"]};
    }}

    /* ── Panels generics ── */
    #InspectorSection {{
        background-color: {pal["card"]};
        border: 1px solid {pal["border"]};
        border-radius: {Radius.MEDIUM}px;
        padding: {Spacing.SM}px;
    }}

    #InspectorLabel {{
        color: {pal["text_secondary"]};
        font-size: {Typography.SIZE_CAPTION}pt;
        font-family: {Typography.FAMILY_BODY};
        font-weight: {Typography.WEIGHT_SEMIBOLD};
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    #InspectorValue {{
        color: {pal["text"]};
        font-size: {Typography.SIZE_BODY}pt;
        font-family: {Typography.FAMILY_BODY};
    }}

    /* ── Command Palette ── */
    #CommandPaletteOverlay {{
        background-color: {Color.BG_OVERLAY};
    }}

    #CommandPaletteInput {{
        background-color: {pal["card"]};
        color: {pal["text"]};
        border: 1px solid {Color.CYAN};
        border-radius: {Radius.LARGE}px;
        padding: {Spacing.MD}px {Spacing.LG}px;
        font-size: {Typography.SIZE_HEADING_1}pt;
        font-family: {Typography.FAMILY_BODY};
    }}

    #CommandItem {{
        background-color: transparent;
        color: {pal["text_secondary"]};
        border: none;
        border-radius: {Radius.SM}px;
        padding: {Spacing.SM}px {Spacing.MD}px;
        font-size: {Typography.SIZE_BODY}pt;
    }}

    #CommandItem:hover,
    #CommandItem:selected {{
        background-color: {Color.CYAN_FAINT};
        color: {pal["text"]};
    }}

    /* ── Chat ── */
    #ChatPage {{
        background-color: {pal["bg"]};
    }}

    #ChatInputBar {{
        background: rgba(10, 15, 30, 0.75);
        border-top: 1px solid rgba(0, 240, 255, 0.08);
    }}

    #ChatInput {{
        background-color: rgba(15, 22, 38, 0.85);
        color: {pal["text"]};
        border: 1px solid rgba(0, 240, 255, 0.12);
        border-radius: {Radius.MEDIUM}px;
        padding: 0 14px;
        font-size: {Typography.SIZE_BODY}pt;
        font-family: {Typography.FAMILY_BODY};
    }}

    #ChatInput:focus {{
        border: 1px solid rgba(0, 240, 255, 0.35);
        background-color: rgba(18, 26, 44, 0.9);
    }}

    #ChatInput::placeholder {{
        color: {pal["text_muted"] if "text_muted" in pal else pal["text_secondary"]};
    }}

    QPushButton#InputAttach,
    QPushButton#InputMic,
    QPushButton#InputSend {{
        background-color: transparent;
        color: {pal["text_secondary"]};
        border: 1px solid rgba(0, 240, 255, 0.08);
        border-radius: {Radius.MEDIUM}px;
        font-size: 16px;
    }}

    QPushButton#InputAttach:hover,
    QPushButton#InputMic:hover,
    QPushButton#InputSend:hover {{
        background-color: {Color.CYAN_FAINT};
        color: {Color.CYAN};
        border-color: rgba(0, 240, 255, 0.25);
    }}

    QPushButton#InputAttach:pressed,
    QPushButton#InputMic:pressed,
    QPushButton#InputSend:pressed {{
        background-color: {Color.CYAN_GLOW};
    }}

    /* ── Dashboard Cards ── */
    #MiniStatCard {{
        background-color: {pal["card"]};
        border: 1px solid {pal["border"]};
        border-radius: {Radius.LARGE}px;
        padding: {Spacing.LG}px;
    }}

    #MiniStatCard:hover {{
        border-color: {Color.CYAN_GLOW};
    }}

    /* ── Generic ── */
    QSplitter::handle {{
        background-color: {pal["border"]};
        width: 1px;
    }}

    /* ── CustomTitleBar ── */
    #CustomTitleBar {{
        background-color: {Color.BG_DEEP};
        border-bottom: 1px solid {pal["border"]};
    }}

    /* ── Notification Popup ── */
    #NotificationPopup {{
        background-color: rgba(8, 12, 28, 0.92);
        border: 1px solid {pal["border"]};
        border-radius: {Radius.LARGE}px;
    }}

    #NotificationItem {{
        color: {pal["text"]};
        font-size: {Typography.SIZE_CAPTION}pt;
        padding: {Spacing.SM}px {Spacing.MD}px;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }}

    #NotificationItem:hover {{
        background-color: {Color.CYAN_FAINT};
    }}

    #NotificationBadge {{
        background-color: {Color.CYAN};
        color: #000;
        border-radius: 8px;
        font-size: {Typography.SIZE_SMALL}pt;
        font-weight: {Typography.WEIGHT_BOLD};
        min-width: 16px;
        min-height: 16px;
    }}

    /* ── Collapsible Section ── */
    #CollapsibleHeader {{
        background-color: transparent;
        color: {pal["text"]};
        border: none;
        border-bottom: 1px solid rgba(255,255,255,0.05);
        padding: {Spacing.SM}px 0;
        font-size: {Typography.SIZE_CAPTION}pt;
        font-weight: {Typography.WEIGHT_SEMIBOLD};
        text-align: left;
    }}

    #CollapsibleHeader:hover {{
        color: {Color.CYAN};
    }}

    /* ── Pages generics ── */
    #PageSection {{
        background-color: {pal["card"]};
        border: 1px solid {pal["border"]};
        border-radius: {Radius.LARGE}px;
        padding: {Spacing.LG}px;
    }}

    #PageCard {{
        background-color: {pal["card"]};
        border: 1px solid {pal["border"]};
        border-radius: {Radius.MEDIUM}px;
        padding: {Spacing.MD}px;
    }}

    #PageCard:hover {{
        border-color: {Color.CYAN_GLOW};
    }}

    #PageTitle {{
        color: {pal["text"]};
        font-size: {Typography.SIZE_HEADING_2}pt;
        font-weight: {Typography.WEIGHT_BOLD};
        font-family: {Typography.FAMILY_DISPLAY};
    }}

    #PageSubtitle {{
        color: {pal["text_secondary"]};
        font-size: {Typography.SIZE_BODY}pt;
    }}

    QScrollBar:vertical {{
        background-color: transparent;
        width: 6px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background-color: {pal["text_muted"] if "text_muted" in pal else pal["border"]};
        border-radius: 3px;
        min-height: 20px;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QToolTip {{
        background-color: {pal["card"]};
        color: {pal["text"]};
        border: 1px solid {Color.CYAN};
        border-radius: {Radius.SM}px;
        padding: {Spacing.XS}px {Spacing.SM}px;
        font-size: {Typography.SIZE_CAPTION}pt;
    }}
    """


def build_sidebar_qss(dark: bool = True) -> str:
    """QSS spécifique à la sidebar (peut être mergé dans build_qss)."""
    return ""  # Tout est déjà dans build_qss pour l'instant
