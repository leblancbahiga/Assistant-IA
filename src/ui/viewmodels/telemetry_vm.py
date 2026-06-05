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

    def __init__(self):
        self._ram_warning_gb = 2.0
        self._ram_critical_gb = 1.0

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

        return TelemetrySnapshot(
            ram_free_mb=free_mb,
            ram_total_mb=total_mb,
            ram_percent=mem.percent,
            ram_status=ram_status,
        )

    def ram_color(self, status: str) -> str:
        return {"ok": "#10B981", "warning": "#F59E0B", "critical": "#EF4444"}.get(status, "#6B7280")
