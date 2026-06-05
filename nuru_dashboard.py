#!/usr/bin/env python3
"""NURU V4.5 — Entry point avec qasync (interface fluide, 0 freezes).

Remplace nuru.py pour le mode dashboard (--chat).
Utilise qasync pour fusionner la boucle asyncio avec Qt.
"""
import sys
import asyncio
from pathlib import Path

# Ajouter src au path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src import setup_logging
from src.config import config
from src.nuru_core import NuruCore


def main():
    setup_logging(config.log_file)

    # Vérifier que qasync est installé
    try:
        from qasync import QEventLoop
    except ImportError:
        print("❌ qasync non installé. Faites: pip install qasync")
        sys.exit(1)

    from PySide6.QtWidgets import QApplication
    from src.ui.dashboard import CyberDashboard

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # NURU V5 : style unifié pour le QSS
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialisation NURU
    core = NuruCore()
    window = CyberDashboard(core)
    window.show()

    print("🚀 NURU V4.5 — Dashboard qasync actif")
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
