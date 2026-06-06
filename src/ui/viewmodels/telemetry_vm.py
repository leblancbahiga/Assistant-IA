"""ViewModel de télémétrie — RAM, tok/s, route pour l'UI."""
import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class TelemetrySnapshot:
    """Instantané des métriques système."""
    ram_free_mb: int = 0
    ram_total_mb: int = 0
    ram_percent: float = 0.0
    tokens_per_sec: float = 0.0
    current_route: str = "idle"
    current_model: str = ""
    rag_score: float = 0.0
    is_busy: bool = False
    ram_status: str = "ok"  # ok | warning | critical


class TelemetryViewModel:
    """Logique d'affichage de la télémétrie système."""

    def __init__(self, runtime_manager=None):
        self._ram_warning_gb = 2.0
        self._ram_critical_gb = 1.0
        self._runtime = runtime_manager  # Bridge to RuntimeManager for TPS

    def set_runtime(self, runtime_manager):
        """Inject the RuntimeManager reference."""
        self._runtime = runtime_manager

    def snapshot(self) -> TelemetrySnapshot:
        """Capture un instantané des métriques actuelles."""
        mem = psutil.virtual_memory()
        free_mb = int(mem.available / (1024 * 1024))
        total_mb = int(mem.total / (1024 * 1024))

        ram_status = "ok"
        free_gb = free_mb / 1024
        if free_gb < self._ram_critical_gb:
            ram_status = "critical"
        elif free_gb < self._ram_warning_gb:
            ram_status = "warning"

        # Read TPS and RAG score from RuntimeManager (if available)
        tps = 0.0
        rag_score = 0.0
        if self._runtime and hasattr(self._runtime, '_last_generation_stats'):
            stats = self._runtime._last_generation_stats
            tps = stats.get('tps', 0.0)
            rag_score = stats.get('rag_score', 0.0)

        return TelemetrySnapshot(
            ram_free_mb=free_mb,
            ram_total_mb=total_mb,
            ram_percent=mem.percent,
            ram_status=ram_status,
            tokens_per_sec=tps,
            rag_score=rag_score,
        )

    def ram_color(self, status: str) -> str:
        return {"ok": "#10B981", "warning": "#F59E0B", "critical": "#EF4444"}.get(status, "#6B7280")
