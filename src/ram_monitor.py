import psutil
import logging
import gc
import os
import asyncio
from typing import Callable, Optional
import time

logger = logging.getLogger(__name__)

class RAMMonitor:
    """
    Surveille la mémoire unifiée (Unified Memory) sur macOS (M1/M2/M3).
    Déclenche des actions de nettoyage (garbage collection, déchargement modaux)
    lorsque la RAM libre devient critique.
    """
    
    def __init__(
        self, 
        warning_threshold_gb: float = 2.0,   # Alerte si < 2 Go libre
        critical_threshold_gb: float = 1.0,  # Action si < 1 Go libre
        check_interval_sec: float = 5.0      # Vérification toutes les 5 sec
    ):
        self.warning_threshold = warning_threshold_gb * 1024 * 1024 * 1024  # GB en bytes
        self.critical_threshold = critical_threshold_gb * 1024 * 1024 * 1024
        self.check_interval = check_interval_sec
        self._generating = False  # NURU V5 : flag pour polling dynamique
        self._callbacks: list[Callable] = []
        self._running = False
        self._task = None
        
        # Affichage de la RAM totale au démarrage
        mem = psutil.virtual_memory()
        logger.info(f"🧠 Mémoire système : {mem.total / (1024**3):.2f} Go total | {mem.available / (1024**3):.2f} Go disponible au départ")

    def register_callback(self, callback: Callable):
        """Enregistre une fonction à appeler en cas de mémoire critique."""
        self._callbacks.append(callback)
        logger.info(f"✅ Callback de libération de mémoire enregistré : {callback.__name__}")

    def get_available_ram_bytes(self) -> float:
        """Retourne la RAM disponible en bytes sur macOS."""
        # psutil.virtual_memory().available est la meilleure estimation sur macOS
        return psutil.virtual_memory().available

    async def check_and_act(self):
        """Vérifie la RAM et déclenche les actions nécessaires (version asynchrone)."""
        available = self.get_available_ram_bytes()
        
        if available < self.critical_threshold:
            logger.warning(f"🚨 RAM CRITIQUE : {available / (1024**3):.2f} Go libre. Nettoyage immédiat...")
            await self._trigger_callbacks(force=True)
        elif available < self.warning_threshold:
            logger.warning(f"⚠️ RAM BASSE : {available / (1024**3):.2f} Go libre. Mode économie activé.")
            await self._trigger_callbacks(force=False)
        else:
            # Log silencieux toutes les 60s pour éviter le spam
            # logger.debug(f"RAM OK : {available / (1024**3):.2f} Go libre")
            pass

    async def _trigger_callbacks(self, force: bool):
        """Appelle tous les callbacks enregistrés pour libérer de la RAM (version asynchrone)."""
        logger.info(f"🧹 Exécution du nettoyage mémoire (Force={force})...")
        
        # 1. Garbage collect Python
        gc.collect()

        # 2. NURU V5 : vider le cache Metal/GPU
        try:
            import mlx.core as mx
            mx.clear_cache()
        except ImportError:
            pass
        try:
            import torch
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except ImportError:
            pass
        
        # 2. Appeler les callbacks métiers (sync ou async)
        coroutines = []
        for cb in self._callbacks:
            try:
                logger.debug(f"  → Appel de callback : {cb.__name__}")
                
                if asyncio.iscoroutinefunction(cb):
                    # Collecter les coroutines pour les exécuter en parallèle
                    coroutines.append(cb(force=force))
                else:
                    # Exécution synchrone directe
                    cb(force=force)
            except Exception as e:
                logger.error(f"❌ Erreur dans callback {cb.__name__}: {e}")
        
        # Attendre que tous les callbacks asynchrones soient terminés
        if coroutines:
            logger.info(f"⏳ Attente de {len(coroutines)} callbacks asynchrones...")
            await asyncio.gather(*coroutines, return_exceptions=True)
            logger.info("✅ Tous les callbacks asynchrones terminés.")

    def start(self):
        """Lance le monitoring en arrière-plan.
        Si aucun event loop n'est en cours, on reporte le démarrage.
        """
        if self._running:
            return
        self._running = True
        logger.info("👀 Monitoring RAM activé (interruption toutes les 5s)")
        
        # Vérifier s'il y a un event loop en cours
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                self._task = asyncio.create_task(self._monitor_loop())
                return
        except RuntimeError:
            # Pas d'event loop → on crée une boucle de fond
            pass
        
        # Fallback : thread ou pas d'event loop
        logger.warning("⚠️ Event loop asynchrone non trouvée, monitoring en mode passif.")
        self._running = False  # On ne force pas, le monitoring sera relancé manuellement
    
    def start_with_loop(self, loop: asyncio.AbstractEventLoop):
        """Démarre le monitoring sur une boucle événementielle spécifique."""
        if self._running:
            return
        self._running = True
        logger.info("👀 Monitoring RAM activé (sur boucle externe)")
        self._task = loop.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        while self._running:
            await self.check_and_act()
            # NURU V5 : polling dynamique — 1s pendant génération, 5s au repos
            interval = 1.0 if self._generating else self.check_interval
            await asyncio.sleep(interval)

    # NURU V5 : signaler le début/fin de génération pour polling dynamique
    def set_generating(self, active: bool):
        self._generating = active
        logger.debug(f"RAM monitor: generation={'active' if active else 'inactive'} → {'1s' if active else f'{self.check_interval}s'} polling")

    def stop(self):
        """Arrête le monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                asyncio.get_event_loop().run_until_complete(self._task)
            except:
                pass
            self._task = None
        logger.info("🛑 Monitoring RAM arrêté.")