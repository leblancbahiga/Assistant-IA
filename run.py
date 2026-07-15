"""
NURU — Point d'entrée unique V16.

Usage :
  python3 run.py                         → Nouvelle UI (USE_NEW_UI=True)
  python3 run.py --legacy                → Ancienne UI (AmbientApp)

Le flag USE_NEW_UI dans src/config.py contrôle la valeur par défaut.
"""

import sys
import os
import logging

# ── Purge PYTHONPATH Hermes (conflit Python 3.11/3.13) ──
_HERMES_MARKERS = ('.hermes/hermes-agent', '.hermes/hermes-agent/venv')
os.environ.pop('PYTHONPATH', None)
sys.path = [p for p in sys.path if not any(m in p for m in _HERMES_MARKERS)]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Feature flag — migré de config.py vers flag explicite ──
USE_NEW_UI = True  # False → ancienne UI. True → nouvelle UI V16.


def build_engine():
    """Construit le moteur de conversation partagé (backend)."""
    from src.core.orchestrator import build_conversation_engine
    return build_conversation_engine()


def launch_legacy():
    """Lance l'ancienne interface AmbientApp (V12-V15)."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon

    logger.info("🚀 NURU V12 — Legacy UI (AmbientApp)")

    app = QApplication(sys.argv)
    app.setApplicationName("NURU")
    app.setOrganizationName("NURU")
    app.setWindowIcon(
        QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png")
    )

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

    logger.info("✅ NURU Legacy prêt")
    return app.exec()


def launch_v16():
    """Lance la nouvelle interface NURU V16 (Command Deck)."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon

    logger.info("🚀 NURU V16 — Command Deck (nouvelle UI)")

    app = QApplication(sys.argv)
    app.setApplicationName("NURU")
    app.setOrganizationName("NURU")
    app.setWindowIcon(
        QIcon("src/ui/assets/Gemini_Generated_Image_35cdt735cdt735cd_transparent.png")
    )

    # Backend
    engine = build_engine()

    # Nouvelle UI
    from src.ui.app import NuruApp
    nuru = NuruApp(app, engine=engine)

    logger.info("✅ NURU V16 prêt — fenêtre unique")
    return nuru.run()


def main():
    if "--legacy" in sys.argv:
        sys.exit(launch_legacy())

    if USE_NEW_UI:
        sys.exit(launch_v16())
    else:
        sys.exit(launch_legacy())


if __name__ == "__main__":
    main()
