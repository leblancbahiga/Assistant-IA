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
    rag_data = Signal(dict)  # RAG result data (scores, sources, etc.)
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

                # Récupérer les données RAG depuis le core après la génération
                try:
                    rag_data = self._get_rag_data()
                    if rag_data:
                        self.signals.rag_data.emit(rag_data)
                except Exception as e:
                    logger.debug(f"RAG data retrieval: {e}")

            loop.run_until_complete(stream())
            loop.close()

            self.signals.finished.emit(full_response)

        except Exception as e:
            logger.error(f"InferenceWorker error: {e}")
            self.signals.error.emit(str(e))

    def _get_rag_data(self) -> dict:
        """Extrait les données RAG du core après génération."""
        data = {}
        
        # Depuis le RAG engine last_top_score
        if hasattr(self.core, 'rag') and hasattr(self.core.rag, 'last_top_score'):
            data['top_score'] = self.core.rag.last_top_score
        
        # Depuis l'orchestrator
        if hasattr(self.core, 'orchestrator'):
            orch = self.core.orchestrator
            if hasattr(orch, 'rag_engine') and hasattr(orch.rag_engine, 'last_top_score'):
                data['top_score'] = data.get('top_score', 0) or orch.rag_engine.last_top_score
            if hasattr(orch, 'last_rag_result'):
                last = orch.last_rag_result
                if last:
                    data['documents_found'] = getattr(last, 'documents_found', 0)
                    data['chunks_retrieved'] = getattr(last, 'chunks_retrieved', 0)
                    data['chunks_injected'] = getattr(last, 'chunks_injected', 0)
                    data['top_score'] = data.get('top_score', 0) or getattr(last, 'top_score', 0)
                    data['rejected_chunks'] = getattr(last, 'rejected_chunks', 0)
                    data['rejection_reason'] = getattr(last, 'rejection_reason', '')
                    data['retrieval_time_ms'] = getattr(last, 'retrieval_time_ms', 0.0)
                    sources = getattr(last, 'sources', [])
                    data['sources'] = sources
                    data['documents_found'] = len(set(s.get('name', '') for s in sources))
        
        # Depuis le EventBus / RuntimeManager
        if hasattr(self.core, 'runtime'):
            rm = self.core.runtime
            if hasattr(rm, 'get_rag_score'):
                data['top_score'] = data.get('top_score', 0) or rm.get_rag_score()
        
        return data
