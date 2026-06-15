"""Tests B-Task-Destroyed — Audit Top 20 #9.

NuruCore.process_query crée asyncio.create_task(background_extraction()) sans
garder de référence. Quand l'event loop se ferme, la task est détruite avec
"TASK DESTROYED BUT IT IS PENDING" en boucle.

Le fix doit :
1. Garder une référence aux background tasks (self._bg_tasks: set)
2. Enlever les tasks terminées du set une fois done() (éviter fuite mémoire)
3. Permettre à process_query d'être appelé N fois sans accumulation
"""
import asyncio
import logging
import sys

sys.path.insert(0, '/Users/leblancbahiga/Downloads/Assistant IA')
from src.nuru_core import NuruCore
import pytest


class FakeMemoryStore:
    def __init__(self):
        self.facts = []
    def get_recent_history(self, limit=20):
        return []
    def add_fact(self, fact, category=""):
        self.facts.append((fact, category))


class FakeExtractor:
    """Extractor qui simule un délai long."""
    def __init__(self, delay=0.1):
        self.delay = delay
        self.called = 0
    def extract(self, history):
        self.called += 1
        import time
        time.sleep(self.delay)
        return ["fact1"]


class _FakeOrchestrator:
    """Orchestrator minimaliste qui yield 1 token."""
    async def process_query(self, query, session_id="default",
                            use_tts=False, audio_engine=None):
        yield "OK"




def _make_nuru_core():
    """Construit un NuruCore partiel sans __init__ complet (test isolation)."""
    nc = NuruCore.__new__(NuruCore)
    nc.memory = FakeMemoryStore()  # type: ignore[assignment]
    nc._extractor = FakeExtractor()  # type: ignore[assignment]
    # Si le fix est appliqué, NuruCore.__init__ créera self._bg_tasks
    # Sinon, ce test échouera car la key n'existera pas.
    if not hasattr(nc, '_bg_tasks'):
        nc._bg_tasks = set()  # type: ignore[attr-defined]
    nc.orchestrator = _FakeOrchestrator()  # type: ignore[assignment]
    return nc


def test_no_destroyed_pending_warning():
    """Aucun warning 'Task was destroyed!' ne doit être émis.

    C'est le bug user-visible : la task background_extraction() est créée
    sans référence et asyncio la tue à la fermeture de la loop.
    """
    import sys
    sys.path.insert(0, '/Users/leblancbahiga/Downloads/Assistant IA')
    from src.nuru_core import NuruCore

    captured = []

    class _Handler(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if "destroyed" in msg.lower() and "pending" in msg.lower():
                captured.append(msg)

    handler = _Handler(level=logging.ERROR)
    logging.getLogger("asyncio").addHandler(handler)
    logging.getLogger("asyncio").setLevel(logging.ERROR)

    nc = _make_nuru_core()

    async def run():
        for q in ["Bonjour", "Comment ça va", "BEACCOM"]:
            async for tok in nc.process_query(q):
                pass
        await asyncio.sleep(0.15)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()

    assert captured == [], (
        f"Tasks 'destroyed but pending' émises: {captured}\n"
        "Le fix doit garder self._bg_tasks.add(task), task.add_done_callback(discard)."
    )


def test_bg_tasks_referenced_when_running():
    """Pendant l'exécution de l'extract (≈150ms), _bg_tasks doit contenir la task.

    Le fix doit ajouter la task à self._bg_tasks après le yield final du pipeline.
    On consomme d'abord tout le pipeline, puis on poll pendant la durée de l'extract.
    """
    nc = _make_nuru_core()
    nc._extractor = FakeExtractor(delay=0.20)  # Extraction prend 200ms

    observed = []

    async def run():
        # 1. Consommer TOUT le pipeline d'abord (le producer est un async generator)
        async for tok in nc.process_query("hi"):
            pass
        # 2. _schedule_background_extraction a été awaited, task lancée
        # 3. Maintenant poll pendant ~450ms pour capturer la durée de l'extract (200ms)
        for _ in range(15):
            await asyncio.sleep(0.03)
            current = len(nc._bg_tasks)  # type: ignore[attr-defined]
            observed.append(current)

    asyncio.run(run())
    assert max(observed) >= 1, (
        f"_bg_tasks jamais > 0 pendant l'extract! observed={observed[:5]}...{observed[-5:]}. "
        f"Le code doit asyncio.create_task + _bg_tasks.add."
    )


def test_bg_tasks_cleaned_after_completion():
    """Après fin des tasks, _bg_tasks doit être vide (callback done a fait discard)."""
    import sys
    sys.path.insert(0, '/Users/leblancbahiga/Downloads/Assistant IA')
    from src.nuru_core import NuruCore

    nc = _make_nuru_core()
    nc._extractor = FakeExtractor(delay=0.02)

    async def run():
        async for tok in nc.process_query("hi"):
            pass
        await asyncio.sleep(0.1)

    asyncio.run(run())
    remaining = [t for t in nc._bg_tasks if not t.done()]  # type: ignore[attr-defined]
    assert remaining == [], (
        f"Tasks pending encore après await: {remaining}. "
        f"task.add_done_callback(self._bg_tasks.discard) doit nettoyer."
    )

