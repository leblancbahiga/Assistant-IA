"""
NURU V12 — Lancement interface Z.ai.

Architecture ambiante :
  - Tray icon (menu bar macOS)
  - FloatingWidget 220×160 (verre dépoli)
  - VoiceOverlay (⌥␣) — WaveformRings + Transcript
  - ChatOverlay (⌘N) — conversation temporaire
  - Pas de fenêtre principale persistante

Usage :
  python3 run_v12.py
"""

import sys
import os
import logging

# ── Purge PYTHONPATH Hermes (conflit Python 3.11/3.13) ──
# Hermès injecte son venv 3.11 dans PYTHONPATH, ce qui brise les imports
# C extensions compilées pour 3.13 (pydantic_core, etc.).
_HERMES_MARKERS = ('.hermes/hermes-agent', '.hermes/hermes-agent/venv')
os.environ.pop('PYTHONPATH', None)
sys.path = [p for p in sys.path if not any(m in p for m in _HERMES_MARKERS)]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon

    logger.info("🚀 NURU V12 — Ambient Presence (Z.ai)")

    app = QApplication(sys.argv)
    app.setApplicationName("NURU")
    app.setOrganizationName("NURU")
    app.setWindowIcon(QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png"))

    # Palette globale
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, "#070A10")
    palette.setColor(palette.ColorRole.WindowText, "#E8ECF1")
    palette.setColor(palette.ColorRole.Base, "#0D1117")
    palette.setColor(palette.ColorRole.Text, "#E8ECF1")
    palette.setColor(palette.ColorRole.Button, "#151B26")
    palette.setColor(palette.ColorRole.ButtonText, "#E8ECF1")
    palette.setColor(palette.ColorRole.Highlight, "#00D4FF")
    palette.setColor(palette.ColorRole.HighlightedText, "#070A10")
    app.setPalette(palette)

    from src.ui.ambient_app import AmbientApp

    _ambient = AmbientApp(app)

    logger.info("✅ NURU V12 prêt — voir FloatingWidget et icône tray")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
