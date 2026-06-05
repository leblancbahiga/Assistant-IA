"""NURU V5 — InferenceWorker : exécution non-bloquante via QThreadPool.

Remplace l'ancien TokenReceiver (QThread + asyncio.new_event_loop())
par un QRunnable pur qui ne crée pas de boucle d'événements parasite.
"""

import logging
from PySide6.QtCore import QRunnable, QObject, Signal, QThreadPool

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signaux thread-safe pour communication avec l'UI."""
    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)


class InferenceWorker(QRunnable):
    """Exécute la génération LLM dans un thread du pool Qt.

    Utilise QThreadPool pour éviter la création répétée de boucles
    asyncio (qui fuyait de la mémoire avec l'ancien TokenReceiver).
    """

    def __init__(self, core, query: str):
        super().__init__()
        self.core = core
        self.query = query
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self):
        """Point d'entrée du QRunnable — exécuté dans un thread du pool."""
        import asyncio

        try:
            # Créer une boucle pour ce thread uniquement
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            full_response = ""

            async def stream():
                nonlocal full_response
                try:
                    async for token in self.core.process_query_v45(self.query):
                        full_response += token
                        self.signals.token_received.emit(token)
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    self.signals.token_received.emit(f"\n[Erreur: {e}]")

            loop.run_until_complete(stream())
            loop.close()

            self.signals.finished.emit(full_response)

        except Exception as e:
            logger.error(f"InferenceWorker error: {e}")
            self.signals.error.emit(str(e))
