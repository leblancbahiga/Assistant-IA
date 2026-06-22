"""CostGuard — Contrôle des coûts API LLM.

Surveille la consommation API, alerte en cas de dépassement,
et peut forcer le fallback vers des modèles gratuits/locaux.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """Enregistrement de consommation."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "tokens": self.prompt_tokens + self.completion_tokens,
            "cost": self.cost,
            "time": self.timestamp,
        }


@dataclass
class CostConfig:
    """Configuration du CostGuard."""
    daily_budget: float = 0.50        # $0.50/jour max
    monthly_budget: float = 10.00     # $10/mois max
    alert_threshold: float = 0.80     # 80% du budget → alerte
    hard_limit: bool = True           # True = bloquer quand budget épuisé
    preferred_free: bool = True       # Préférer modèles gratuits
    log_path: Path = Path.home() / ".nuru" / "cost_log.jsonl"


@dataclass
class CostGuard:
    """Garde-fou des coûts API.

    Usage :
        guard = CostGuard()
        guard.record_usage("groq/llama-3.3-70b", 500, 200, 0.0007)
        if guard.can_spend(0.001):
            print("Budget OK")
        else:
            print("Budget épuisé, fallback modèle local !")
    """

    config: CostConfig = field(default_factory=CostConfig)
    _records: list[UsageRecord] = field(default_factory=list)
    _on_alert: Optional[Callable[[str], None]] = None

    def __post_init__(self):
        self._load_history()

    def _load_history(self) -> None:
        """Charge l'historique des coûts depuis le fichier journal."""
        if self.config.log_path.exists():
            try:
                for line in self.config.log_path.read_text().strip().split("\n"):
                    if line:
                        data = json.loads(line)
                        self._records.append(UsageRecord(**data))
            except Exception as e:
                logger.error(f"Erreur chargement historique coûts: {e}")

    def _save_record(self, record: UsageRecord) -> None:
        """Sauvegarde un enregistrement."""
        self.config.log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config.log_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Erreur sauvegarde coût: {e}")

    def record_usage(self, model: str, prompt_tokens: int,
                     completion_tokens: int, cost: float) -> UsageRecord:
        """Enregistre une utilisation.

        Returns:
            UsageRecord créé
        """
        record = UsageRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
        )
        self._records.append(record)
        self._save_record(record)

        # Vérifier les seuils
        daily = self.daily_cost
        monthly = self.monthly_cost

        if daily >= self.config.daily_budget * self.config.alert_threshold:
            msg = f"⚠️ Alerte coût: {daily:.3f}$/{self.config.daily_budget}$ aujourd'hui"
            logger.warning(msg)
            if self._on_alert:
                self._on_alert(msg)

        if self.config.hard_limit and daily >= self.config.daily_budget:
            logger.warning("Budget quotidien épuisé ! Fallback forcé.")

        return record

    def can_spend(self, estimated_cost: float) -> bool:
        """Vérifie si le budget permet une dépense.

        Args:
            estimated_cost: Coût estimé de l'opération

        Returns:
            True si le budget le permet
        """
        if not self.config.hard_limit:
            return True

        daily = self.daily_cost
        return (daily + estimated_cost) <= self.config.daily_budget

    @property
    def daily_cost(self) -> float:
        """Coût accumulé aujourd'hui."""
        today = time.time() - 86400
        return sum(r.cost for r in self._records if r.timestamp >= today)

    @property
    def monthly_cost(self) -> float:
        """Coût accumulé ce mois."""
        thirty_days = time.time() - 30 * 86400
        return sum(r.cost for r in self._records if r.timestamp >= thirty_days)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self._records)

    def get_recent_usage(self, hours: int = 24) -> list[UsageRecord]:
        """Usage récent (N dernières heures)."""
        cutoff = time.time() - hours * 3600
        return [r for r in self._records if r.timestamp >= cutoff]

    def get_summary(self) -> dict:
        return {
            "daily_cost": round(self.daily_cost, 4),
            "monthly_cost": round(self.monthly_cost, 4),
            "total_cost": round(self.total_cost, 4),
            "daily_budget": self.config.daily_budget,
            "monthly_budget": self.config.monthly_budget,
            "daily_remaining": round(max(0, self.config.daily_budget - self.daily_cost), 4),
            "n_requests_today": sum(1 for r in self._records if r.timestamp >= time.time() - 86400),
        }

    def reset_daily(self) -> None:
        """Réinitialise le compteur quotidien (pour test)."""
        cutoff = time.time() - 86400
        self._records = [r for r in self._records if r.timestamp < cutoff]

    def set_alert_callback(self, callback: Callable[[str], None]) -> None:
        self._on_alert = callback
