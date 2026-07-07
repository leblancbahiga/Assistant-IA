#!/bin/bash
# NURU V8+ Dashboard Launcher
# Lance le dashboard dans un terminal séparé, indépendant de Hermes

cd "$(dirname "$0")"

# Nettoyer PYTHONPATH Hermes pour éviter conflit Python 3.11/3.13
unset PYTHONPATH

# Rediriger les logs
exec > /tmp/nuru_dashboard.log 2>&1

echo "=== NURU V8+ Dashboard ==="
echo "Démarrage à $(date)"
echo "Python: $(.venv/bin/python3 --version)"

.venv/bin/python3 -c "
import sys
sys.path.insert(0, '.')

from src.ui.dashboard import CyberDashboard
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

core = None
try:
    from src.nuru_core import NuruCore
    core = NuruCore()
    print('NuruCore initialisé — mode réel')
except Exception as e:
    print(f'NuruCore non disponible: {e} — mode démo')

win = CyberDashboard(core=core)
win.show()
win.raise_()
win.activateWindow()
print(f'Dashboard lancé — PID: {__import__(\"os\").getpid()}')
sys.stdout.flush()

app.exec()
"
