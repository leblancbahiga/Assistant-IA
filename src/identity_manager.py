"""IdentityManager V12 — Gère l'identité non-versionnée de l'utilisateur.

Stocke et charge l'identité depuis ~/.nuru/identity.json pour éviter les fuites de données dans git.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_IDENTITY = {
    "user_name": "Leblanc",
    "user_full_name": "Leblanc BAHIGA Mudarhi",
    "user_profession": "Ingénieur agronome & informaticien",
    "user_specialty": "des chaînes de valeur agricoles en Afrique centrale et orientale",
    "user_organizations": "IITA, FAO, World Bank, USAID"
}

class IdentityManager:
    """Gère le chargement et la sauvegarde de l'identité de l'utilisateur."""

    _cached_identity: Dict[str, str] = None

    @classmethod
    def get_identity_path(cls) -> Path:
        """Retourne le chemin vers le fichier d'identité."""
        return Path.home() / ".nuru" / "identity.json"

    @classmethod
    def load(cls) -> Dict[str, str]:
        """Charge l'identité de l'utilisateur.
        
        Si le fichier n'existe pas, il est créé avec les valeurs par défaut.
        """
        if cls._cached_identity is not None:
            return cls._cached_identity

        path = cls.get_identity_path()
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_IDENTITY, f, indent=2, ensure_ascii=False)
                logger.info(f"Identity file created at {path}")
                cls._cached_identity = DEFAULT_IDENTITY.copy()
            except Exception as e:
                logger.error(f"Error creating default identity file: {e}")
                return DEFAULT_IDENTITY.copy()
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # S'assurer que toutes les clés attendues sont présentes
                identity = DEFAULT_IDENTITY.copy()
                for key, val in DEFAULT_IDENTITY.items():
                    if key in data and str(data[key]).strip():
                        identity[key] = str(data[key]).strip()
                cls._cached_identity = identity
            except Exception as e:
                logger.error(f"Error reading identity file: {e}")
                return DEFAULT_IDENTITY.copy()

        return cls._cached_identity

    @classmethod
    def clear_cache(cls):
        """Efface le cache pour forcer un rechargement."""
        cls._cached_identity = None
