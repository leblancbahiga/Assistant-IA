#!/usr/bin/env python3
"""NURU V5/V6 — Entry point avec qasync, Daemon Continu et Télémétrie RAM.

Intègre la boucle asyncio avec Qt pour une interface fluide,
et lance les agents de fond (Auto-Fetch, Synchro Wiki, Learning Loop)
sans bloquer l'UI.

Inspiré des architectures "Continuous Agent" (OpenJarvis) et
"Auto-fetch toutes les 20 min" (OpenHuman).
"""
import sys
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src import setup_logging
from src.config import config
from src.nuru_core import NuruCore

logger = logging.getLogger(__name__)

# ── Intervalle du daemon continu (secondes) ──
DAEMON_TICK = 60  # Vérification toutes les 60s (pas 20 min pour le debug)
AUTO_FETCH_INTERVAL = 1200  # 20 minutes pour l'auto-fetch

# ── Seuils mémoire ──
RAM_CRITICAL_GB = 0.8   # Suspendre les tâches de fond si < 0.8 Go libre
RAM_WARNING_GB = 1.5    # Alerte si < 1.5 Go libre


async def continuous_background_daemon(core: NuruCore):
    """Boucle de fond continue (Continuous Agent).

    S'exécute silencieusement — Auto-Fetch, Learning Loop, synchro Wiki.
    Vérifie la pression mémoire avant chaque tâche lourde.
    """
    logger.info(">> Daemon continu activé (Auto-Fetch, Learning, Wiki Sync).")

    background_started = False
    tick_count = 0
    auto_fetch_ok = hasattr(core, 'auto_fetcher') and core.auto_fetcher is not None

    while True:
        try:
            # 0. Au premier tick, lancer les tâches de fond de NuruCore
            #    (maintenant que la boucle asyncio tourne)
            if not background_started:
                core.start_background_tasks()
                background_started = True
                logger.info(">> Tâches de fond NuruCore démarrées")

            # 1. Vérification RAM
            import psutil
            free_gb = psutil.virtual_memory().available / (1024**3)

            if free_gb < RAM_CRITICAL_GB:
                logger.warning(
                    f">> [ALERTE RAM] {free_gb:.2f} Go libre. "
                    f"Tâches de fond suspendues."
                )
                await asyncio.sleep(DAEMON_TICK)
                tick_count += 1
                continue

            # 2. Auto-Fetch (toutes les 20 min)
            if auto_fetch_ok and tick_count % (AUTO_FETCH_INTERVAL // DAEMON_TICK) == 0:
                logger.info(">> Auto-Fetch: scan des nouveaux fichiers...")
                try:
                    await core.auto_fetcher.scan_and_index()
                except Exception as e:
                    logger.error(f">> Auto-Fetch error: {e}")

            # 3. Learning Loop : mining periodique (toutes les 10 min)
            if (hasattr(core, 'orchestrator')
                    and hasattr(core.orchestrator, 'trace_collector')
                    and tick_count % 10 == 0):
                tc = core.orchestrator.trace_collector
                count = tc.count()
                if count > 0 and count % 20 == 0:
                    logger.info(f">> Learning Loop: {count} traces collectées")
                    # Déclencher le mining asynchrone
                    try:
                        from src.learning.miner import MiningWorker
                        miner = MiningWorker(trace_collector=tc)
                        report = await miner.generate_report()
                        logger.info(f">> Mining report:\n{report}")
                    except Exception as e:
                        logger.debug(f">> Mining skip: {e}")

            # 4. Synchro Nuru_Brain (toutes les 5 min)
            if (hasattr(core, 'ingestion')
                    and tick_count % 5 == 0):
                logger.debug(">> Wiki sync: heartbeat OK")

        except Exception as e:
            logger.error(f">> [ERREUR DAEMON] {e}")

        await asyncio.sleep(DAEMON_TICK)
        tick_count += 1


def main():
    setup_logging(config.log_file)

    # Vérifier qasync
    try:
        from qasync import QEventLoop
    except ImportError:
        print("❌ qasync non installé. Faites: pip install qasync")
        sys.exit(1)

    from PySide6.QtWidgets import QApplication
    from src.ui.dashboard import CyberDashboard
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # NURU V5 : style unifié pour le QSS
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialisation NURU
    logger.info(">> Initialisation du NuruCore...")
    core = NuruCore()
    # Ne pas appeler start_background_tasks() ici — pas de boucle event loop
    # Les tâches de fond sont lancées par le daemon continu

    # Activation de l'Auto-Fetch (optionnel, selon config)
    if config.auto_fetch_enabled:
        try:
            from src.auto_fetch import AutoFetcher
            core.auto_fetcher = AutoFetcher(
                index_callback=core.ingestion.index_file,
                enabled=True,
            )
            logger.info(">> Auto-Fetch activé")
        except Exception as e:
            logger.warning(f">> Auto-Fetch non disponible: {e}")
            core.auto_fetcher = None
    else:
        core.auto_fetcher = None

    # Chargement de l'UI
    window = CyberDashboard(core)
    window.show()

    logger.info("🚀 NURU V5/V6 — Dashboard qasync actif")

    # Lancement de la boucle asynchrone principale
    with loop:
        # Attacher le daemon d'arrière-plan
        loop.create_task(continuous_background_daemon(core))
        loop.run_forever()


if __name__ == "__main__":
    main()
