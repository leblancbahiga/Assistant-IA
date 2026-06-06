"""NURU V5 — Configuration globale.

Charge config/settings.yaml (clés non-sensibles) + Keychain macOS (clés API).
Accès via le singleton `config`.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import keyring
import yaml


class Config(BaseSettings):
    """Configuration globale de NURU V5.

    Priorité : settings.yaml > valeurs par défaut > variables d'environnement.
    Les clés API sont lues depuis le Keychain macOS (ne jamais les mettre dans YAML).
    """

    # ── Chemins ──
    base_dir: Path = Path(__file__).parent.parent
    data_dir: Path = base_dir / "data"
    index_path: Path = base_dir / "indexes" / "nuru.db"
    model_dir: Path = base_dir / "models"
    log_file: Path = base_dir / "logs" / "nuru.log"
    config_path: Path = base_dir / "config" / "settings.yaml"

    # ── Mode de réponse (NURU V5) ──
    response_mode: str = "hybrid"  # strict | hybrid | free

    # ── LLM Locaux ──
    local_model: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    local_model_fallback: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

    # ── Cloud ──
    cloud_model: str = "llama-3.3-70b-versatile"
    cloud_provider: str = "groq"
    cloud_fallback: str = "openrouter/deepseek/deepseek-v4-flash"

    # ── RAG ──
    rag_k: int = 5
    rag_score_threshold: float = 0.50
    rag_score_fallback: float = 0.40
    rag_max_context_tokens: int = 600
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Cache ──
    cache_ttl_seconds: int = 300
    cache_maxsize: int = 256

    # ── TokenJuice (NURU V6) ──
    token_juice_enabled: bool = True
    token_juice_max_chunk_chars: int = 2000

    # ── Learning Loop (NURU V6) ──
    learning_enabled: bool = True

    # ── Dual-Write / Nuru_Brain (NURU V6) ──
    nuru_brain_enabled: bool = True
    nuru_brain_path: str = os.path.expanduser("~/Nuru_Brain")
    nuru_brain_watch_enabled: bool = False

    # ── Auto-Fetch (NURU V6) ──
    auto_fetch_enabled: bool = False
    auto_fetch_interval_min: int = 30

    # ── Stratégies Hybrides (NURU V6) ──
    hybrid_mode: str = "local_only"  # local_only | verify | plan | rag

    # ── Mémoire ──
    session_window: int = 5

    # ── Audio ──
    stt_model: str = "small"
    tts_enabled: bool = True
    tts_engine: str = "piper"

    # ── Clés API (via Keychain macOS uniquement) ──

    @property
    def deepseek_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "deepseek")

    @property
    def openrouter_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "openrouter")

    @property
    def groq_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "groq")

    @property
    def gemini_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "gemini")

    @property
    def brave_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "brave")

    @property
    def tavily_key(self) -> Optional[str]:
        return keyring.get_password("com.nuru.assistant", "tavily")

    def get_model_path(self, model_id: str) -> str:
        """Retourne le chemin local si le modèle existe, sinon l'ID HuggingFace."""
        model_name = model_id.split("/")[-1]
        local_path = self.model_dir / model_name
        if local_path.exists():
            return str(local_path)
        return model_id

    def load_yaml(self) -> dict:
        """Charge et fusionne les valeurs depuis config/settings.yaml."""
        yaml_path = self.config_path
        if not yaml_path.exists():
            return {}

        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

        # Appliquer les valeurs du YAML, conserver les chemins et clés API
        for key, value in data.items():
            if hasattr(self, key) and not key.endswith("_key") and not key.startswith("base_"):
                setattr(self, key, value)

        return data

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_prefix="NURU_",
    )


# Singleton
config = Config()
# Charger le YAML (peut surcharger les valeurs par défaut)
try:
    config.load_yaml()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible de charger settings.yaml: {e}")
