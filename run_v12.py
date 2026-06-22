#!/usr/bin/env python3
"""
NURU V12 — Nouveau lanceur (design Z.ai).

Remplace l'ancien CyberDashboard 3 colonnes par l'interface
NuruWindow : PresenceOrb + ConversationSurface + InputBar.

Usage :
    python3 run_v12.py
"""

import sys
import os
import logging

# Path setup
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_v12")


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from src.ui.nuru_window import NuruWindow

    app = QApplication(sys.argv)

    # Police par défaut
    font = QFont("Inter", 13)
    app.setFont(font)

    # Style général (QSS de base — les composants ont leur propre style)
    app.setStyle("Fusion")

    window = NuruWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
