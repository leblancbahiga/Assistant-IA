"""ConversationEngine — Pont UI ↔ Backend NURU (V12).

Bridge asynchrone entre les composants PySide6 (ConversationSurface,
NuruInputBar, NuruPresenceOrb) et le pipeline LLM (NuruOrchestrator).

Architecture :
  - Thread asyncio dédié pour le backend (pas de blocage UI)
  - Signaux PySide6 pour le streaming de tokens
  - Gestion d'état OrbState : IDLE → THINKING → SPEAKING → IDLE
  - Support multi-session

Usage :
  engine = ConversationEngine()
  engine.start()
  engine.send_message("Bonjour NURU")
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

from src.nuru_core import NuruCore
from src.kernel import NuruKernel
from src.ui.presence_orb import OrbState

logger = logging.getLogger(__name__)

# Phase 3 — Noyau central
_kernel = NuruKernel()


class ConversationEngine(QObject):
    """Bridge entre l'interface PySide6 et le pipeline asynchrone NURU.

    Émet des signaux thread-safe pour mettre à jour l'UI en temps réel
    pendant la génération des réponses.
    """

    # ── Signaux ──
    # Chaque token de réponse (streaming)
    token_received = Signal(str)
    # Signal de fin avec le texte complet
    response_complete = Signal(str)
    # Erreur survenue
    error_occurred = Signal(str, str)  # (code, message)
    # Changement d'état de l'orb
    state_changed = Signal(object)  # OrbState
    # Stratégie pipeline (routing / rag / generation / completed)
    strategy_changed = Signal(str)
    # Métadonnées de réponse (confidence, sources, durée, etc.)
    response_metadata = Signal(object)  # dict
    # Transcription vocale temps réel
    voice_transcript = Signal(str)
    # Session vocale terminée avec le texte final
    voice_session_end = Signal(str)
    # V17 P0-C : signalée quand l'init asynchrone (NuruCore) est terminée
    backend_ready = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._nuru: NuruCore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = False
        self._current_session: str = "default"
        self._processing = False
        # Cache de session pour réutilisation
        self._sessions: dict[str, str] = {}
        # Évite de surcharger les signaux pendant le démarrage
        self._started = False
        self._voice_running = False
        self._voice_buffer: list[str] = []

    # ── Cycle de vie ──

    def start(self) -> None:
        """Initialise NuruCore dans le thread asyncio (pas de blocage UI)."""
        if self._started:
            logger.warning("ConversationEngine déjà démarré")
            return

        logger.info("🚀 ConversationEngine — démarrage thread asyncio...")
        self.state_changed.emit(OrbState.THINKING)

        # V16 FIX : Créer le thread asyncio AVANT NuruCore pour éviter
        # le blocage de l'UI (15-20s de freeze). NuruCore est construit
        # dans _init_async sur le thread asyncio dédié.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_async_loop,
            name="nuru-asyncio",
            daemon=True,
        )
        self._thread.start()

        # Construire NuruCore dans le thread asyncio
        future = asyncio.run_coroutine_threadsafe(
            self._init_async(),
            self._loop,
        )
        future.add_done_callback(self._on_init_done)

    def _run_async_loop(self) -> None:
        """Boucle asyncio du thread dédié."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _init_async(self) -> None:
        """Récupère NuruCore depuis le kernel ou le crée si besoin."""
        try:
            # Essayer de récupérer NuruCore existant
            self._nuru = _kernel.get("nuru_core")
            logger.info("✅ NuruCore récupéré depuis le Kernel")
        except KeyError:
            # V17 P9: si NuruCore n'existe pas encore, le créer maintenant
            logger.info("⚙️ NuruCore non trouvé dans le kernel — création")
            self._nuru = NuruCore()
            logger.info("✅ NuruCore créé et enregistré dans le Kernel")
        try:
            self._nuru.start_background_tasks()
            logger.info("✅ Tâches background NuruCore démarrées")
        except Exception as e:
            logger.error(f"⚠️ Échec démarrage tâches background: {e}")
            raise

    def _on_init_done(self, future: asyncio.Future) -> None:
        """Callback quand l'init asynchrone est terminée."""
        try:
            future.result()
            self._ready = True
            self._started = True
            self.state_changed.emit(OrbState.IDLE)
            # V17 P0-C : signaler aux pages que l'engine est prêt (reconstruction lazy)
            self.backend_ready.emit()
            logger.info("✅ ConversationEngine prêt — signal ready émis")
        except Exception as e:
            logger.error(f"❌ Échec init asynchrone: {e}")
            self.error_occurred.emit("async_init", str(e))
            self.state_changed.emit(OrbState.ERROR)

    def stop(self) -> None:
        """Arrête la boucle asyncio et libère les ressources."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._started = False
        self._ready = False
        logger.info("🛑 ConversationEngine arrêté")

    # ── API publique ──

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def is_processing(self) -> bool:
        return self._processing

    @property
    def session_id(self) -> str:
        return self._current_session

    @property
    def nuru(self) -> NuruCore | None:
        """Accès au backend NuruCore (services mémoire, RAG, etc.)."""
        return self._nuru

    @property
    def memory_store(self):
        """MemoryStore du backend."""
        return self._nuru.memory if self._nuru else None

    @property
    def rag_engine(self):
        """RAGEngine du backend."""
        return self._nuru.rag if self._nuru else None

    @property
    def ingestion(self):
        """IngestionEngine du backend (indexation de documents)."""
        return self._nuru.ingestion if self._nuru else None

    @property
    def orchestrator(self):
        """NuruOrchestrator du backend."""
        return self._nuru.orchestrator if self._nuru else None

    @property
    def model_router(self):
        """ModelRouter du backend."""
        return self._nuru.model_router if hasattr(self._nuru, 'model_router') and self._nuru else None

    @property
    def mcp_client(self):
        """MCPClient pour outils externes."""
        return self._nuru.mcp_client if hasattr(self._nuru, 'mcp_client') and self._nuru else None

    @property
    def mcp_server(self):
        """MCPServer exposant les outils internes."""
        return self._nuru.mcp_server if hasattr(self._nuru, 'mcp_server') and self._nuru else None

    @property
    def proactive_engine(self):
        """ProactiveEngine pour agents et routines."""
        return self._nuru.proactive if hasattr(self._nuru, 'proactive') and self._nuru else None

    @property
    def routine_scheduler(self):
        """RoutineScheduler pour tâches planifiées."""
        return self._nuru.routines if hasattr(self._nuru, 'routines') and self._nuru else None

    @property
    def current_model_name(self) -> str:
        """Nom du modèle actif."""
        if self._nuru and hasattr(self._nuru, 'config'):
            return getattr(self._nuru.config, 'model', getattr(self._nuru.config, 'local_model', 'qwen2.5:3b'))
        return "qwen2.5:3b"

    @property
    def current_provider(self) -> str:
        """Fournisseur actif."""
        if self._nuru and hasattr(self._nuru, 'config'):
            return getattr(self._nuru.config, 'provider', getattr(self._nuru.config, 'mode', 'local'))
        return "local"

    def new_session(self, session_id: str | None = None) -> str:
        """Crée ou bascule vers une nouvelle session."""
        sid = session_id or f"session_{int(time.time())}"
        self._current_session = sid
        self._sessions[sid] = sid
        return sid

    def send_message(self, text: str) -> None:
        """Point d'entrée principal : envoie un message au backend.

        Peut être appelé depuis n'importe quel thread (Qt ou non).
        La réponse arrive via les signaux token_received / response_complete.
        """
        if not text or not text.strip():
            return
        if not self._ready:
            logger.warning("ConversationEngine pas encore prêt")
            self.error_occurred.emit("not_ready", "Le moteur NURU n'est pas encore prêt")
            return
        if self._processing:
            logger.warning("Déjà en train de traiter — message ignoré")
            self.error_occurred.emit("busy", "NURU est déjà en train de répondre")
            return

        self._processing = True
        self._safe_emit(self.state_changed, OrbState.THINKING)

        # Lancer le traitement dans le thread asyncio
        asyncio.run_coroutine_threadsafe(
            self._process(text),
            self._loop,
        )

    # ── Voice ──

    def start_voice_session(self) -> None:
        """Démarre la capture micro + STT dans le thread asyncio."""
        if not self._ready or not self._loop:
            return
        self.state_changed.emit(OrbState.LISTENING)
        self._voice_running = True
        self._voice_buffer: list[str] = []
        asyncio.run_coroutine_threadsafe(
            self._run_voice_capture(),
            self._loop,
        )
        logger.info("🎤 Session vocale démarrée")

    def stop_voice_session(self, final_text: str = "") -> None:
        """Arrête la capture micro."""
        self._voice_running = False
        self.state_changed.emit(OrbState.IDLE)
        if final_text.strip():
            self.voice_session_end.emit(final_text)
        logger.info("🎤 Session vocale terminée")

    async def _run_voice_capture(self) -> None:
        """Async generator : capture micro → VAD → STT → signaux UI."""
        audio = self._nuru.audio
        try:
            async for chunk, is_speech in audio.capture_mic():
                if not self._voice_running:
                    break
                if is_speech and chunk is not None:
                    # Écrire le chunk dans un buffer audio
                    audio_path = Path(f"/tmp/nuru_voice_{int(time.time())}.wav")
                    import soundfile as sf
                    sf.write(audio_path, chunk, 16000)
                    # Transcrire
                    text = await audio.transcribe(audio_path)
                    if text.strip():
                        self._voice_buffer.append(text)
                        self._safe_emit(self.voice_transcript, text)
                    # Nettoyer
                    try:
                        audio_path.unlink()
                    except OSError:
                        pass
                # Petite pause pour ne pas saturer
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"🎤 Erreur capture vocale: {e}")
        finally:
            logger.info("🎤 Capture vocale terminée")

    # ── Traitement interne ──

    async def _process(self, text: str) -> None:
        """Exécute le pipeline complet dans le thread asyncio.

        Yields tokens → émet signaux thread-safe vers l'UI.
        """
        full_response = ""
        first_token = True
        # Stockage des métadonnées reçues via EventBus
        _metadata: dict = {}

        # S'abonner aux étapes du pipeline EventBus
        def _on_pipeline_step(data):
            step = data.get("step", "thinking") if isinstance(data, dict) else "thinking"
            self._safe_emit(self.strategy_changed, step)

        # S'abonner aux métadonnées de fin de génération
        def _on_generation_complete(data):
            nonlocal _metadata
            if isinstance(data, dict):
                _metadata = data

        bus = _kernel.get('event_bus')  # Phase 3 — via kernel
        bus.subscribe("pipeline.step", _on_pipeline_step)
        bus.subscribe("generation_complete", _on_generation_complete)

        # Émettre l'état initial "routing"
        self._safe_emit(self.strategy_changed, "routing")

        try:
            # V17 FIX : pipeline Kernel (steps composables) au lieu
            # de self._nuru.orchestrator.process_query() direct
            pipeline = _kernel.get("pipeline")
            async for token in pipeline.run_stream(
                text,
                session_id=self._current_session,
            ):
                full_response += token
                self._safe_emit(self.token_received, token)
                if first_token:
                    first_token = False
                    self._safe_emit(self.strategy_changed, "generation")

            # Finalisation
            self._safe_emit(self.strategy_changed, "completed")
            self._safe_emit(self.response_metadata, _metadata)
            self._safe_emit(self.response_complete, full_response)
            self._safe_emit(self.state_changed, OrbState.IDLE)

        except asyncio.CancelledError:
            logger.info("Requête annulée")
            self._safe_emit(self.state_changed, OrbState.IDLE)

        except Exception as e:
            logger.error(f"❌ Erreur traitement: {e}", exc_info=True)
            self._safe_emit(self.error_occurred, "processing", str(e))
            self._safe_emit(self.state_changed, OrbState.ERROR)

        finally:
            bus.unsubscribe("pipeline.step", _on_pipeline_step)
            bus.unsubscribe("generation_complete", _on_generation_complete)
            self._processing = False

    # ── Helpers ──

    def _safe_emit(self, signal, value) -> None:
        """Émet un signal PySide6 depuis n'importe quel thread.

        V17 P0-C : les signaux PySide6 gèrent nativement le marshaling
        inter-threads via QueuedConnection automatique. Pas besoin de
        QTimer.singleShot (qui ne fonctionne que depuis un thread avec
        une QEventLoop active, ce que n'a pas le thread nuru-asyncio).
        """
        signal.emit(value)
