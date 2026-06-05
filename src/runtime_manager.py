import asyncio
import psutil
import logging
import gc
import time
import mlx.core as mx
from typing import Dict, Any, Optional
from src.core.events import EventBus

logger = logging.getLogger(__name__)

class RuntimeManager:
    """Gère l'état global du runtime, la RAM et l'ordonnancement des tâches."""
    
    TASK_PRIORITY = {
        "stt": 100,
        "generation": 90,
        "retrieval": 70,
        "tts": 60,
        "indexing": 20
    }

    def __init__(self):
        self.event_bus = EventBus()
        self._is_busy = False
        self._current_task_type: Optional[str] = None
        self.ram_threshold_gb = 0.3
        self._last_generation_stats = {
            "tokens": 0,
            "tokens_prompt": 0,
            "context_used": 0,
            "context_max": 4096,
            "seconds": 0.0,
            "tps": 0.0,
            "model": "N/A",
            "model_path": "",
            "route": "LOCAL",
            "rag_score": 0.0,
            "temperature": 0.7,
        }
        self._latency_history: list[float] = []
        self._current_temperature = 0.7

    def get_free_ram(self) -> float:
        """Retourne la RAM disponible en Go."""
        return psutil.virtual_memory().available / (1024**3)

    def check_ram_safety(self) -> bool:
        """Vérifie si on peut exécuter une inférence locale sans crash."""
        free_ram = self.get_free_ram()
        if free_ram < self.ram_threshold_gb:
            logger.warning(f"RAM Critique : {free_ram:.2f} Go. Inférence locale bloquée.")
            self.event_bus.emit_sync("low_memory", {"free_ram": free_ram})
            return False
        return True

    async def schedule_task(self, task_type: str, coro):
        """Planifie une tâche (coroutine) selon sa priorité et mesure la performance."""
        if task_type == "generation":
            if not self.check_ram_safety():
                raise RuntimeError("RAM insuffisante pour l'inférence locale. Basculez en mode Cloud.")
        
        self._is_busy = True
        self._current_task_type = task_type
        start_time = time.time()
        
        try:
            result = await coro
            latency = time.time() - start_time
            
            # Émission d'événement de performance
            asyncio.create_task(self.event_bus.emit("performance_metric", {
                "task_type": task_type,
                "latency_s": round(latency, 2),
                "ram_free_gb": round(self.get_free_ram(), 2)
            }))
            
            return result
        finally:
            self._is_busy = False
            self._current_task_type = None
            # Nettoyage préventif après des tâches lourdes
            if task_type in ["generation", "stt"]:
                gc.collect()
                mx.clear_cache()

    async def schedule_generator(self, task_type: str, gen):
        """Planifie une tâche (générateur async) et yield ses résultats."""
        if task_type == "generation":
            if not self.check_ram_safety():
                raise RuntimeError("RAM insuffisante pour l'inférence locale. Basculez en mode Cloud.")
        
        self._is_busy = True
        self._current_task_type = task_type
        start_time = time.time()
        
        try:
            async for item in gen:
                yield item
            
            latency = time.time() - start_time
            asyncio.create_task(self.event_bus.emit("performance_metric", {
                "task_type": task_type,
                "latency_s": round(latency, 2),
                "ram_free_gb": round(self.get_free_ram(), 2)
            }))
        finally:
            self._is_busy = False
            self._current_task_type = None
            if task_type in ["generation", "stt"]:
                gc.collect()
                mx.clear_cache()

    def update_generation_stats(self, tokens: int, seconds: float, model: str = "N/A", route: str = "LOCAL", rag_score: float = 0.0,
                                temperature: float = 0.7, tokens_prompt: int = 0, context_max: int = 4096, model_path: str = ""):
        """Met à jour les statistiques complètes du cockpit."""
        tps = tokens / seconds if seconds > 0 else 0
        self._current_temperature = temperature
        self._latency_history.append(seconds)
        if len(self._latency_history) > 50:
            self._latency_history.pop(0)
        avg_latency = sum(self._latency_history) / len(self._latency_history) if self._latency_history else 0.0
        self._last_generation_stats = {
            "tokens": tokens,
            "tokens_prompt": tokens_prompt,
            "context_used": tokens_prompt,
            "context_max": context_max,
            "seconds": round(seconds, 2),
            "tps": round(tps, 2),
            "model": model,
            "model_path": model_path,
            "route": route,
            "rag_score": round(rag_score, 2),
            "temperature": temperature,
            "avg_latency": round(avg_latency, 2),
        }

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état actuel pour l'overlay cockpit."""
        ram = psutil.virtual_memory()
        return {
            "ram_free_gb": round(self.get_free_ram(), 2),
            "ram_percent": ram.percent,
            "ram_total_gb": round(ram.total / (1024**3), 1),
            "ram_used_gb": round((ram.total - ram.available) / (1024**3), 1),
            "is_busy": self._is_busy,
            "current_task": self._current_task_type,
            "temperature": self._current_temperature,
            "avg_latency": self._last_generation_stats.get("avg_latency", 0.0),
            "stats": self._last_generation_stats
        }

    def set_temperature(self, temp: float):
        self._current_temperature = temp
