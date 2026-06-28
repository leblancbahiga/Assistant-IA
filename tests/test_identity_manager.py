"""
Test unitaire de IdentityManager.
Verifie la creation du fichier, le chargement, et le cache.
"""
import json
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest

from src.identity_manager import IdentityManager, DEFAULT_IDENTITY

@pytest.fixture(autouse=True)
def clean_cache():
    """Efface le cache d'identité avant et après chaque test."""
    IdentityManager.clear_cache()
    yield
    IdentityManager.clear_cache()

def test_get_identity_path():
    path = IdentityManager.get_identity_path()
    assert isinstance(path, Path)
    assert path.name == "identity.json"

def test_load_default_identity(tmp_path):
    # Mock du chemin pour utiliser un dossier temporaire
    target_path = tmp_path / "identity.json"
    with patch.object(IdentityManager, 'get_identity_path', return_value=target_path):
        identity = IdentityManager.load()
        
        # Le fichier a dû être créé
        assert target_path.exists()
        
        # Le contenu correspond aux valeurs par défaut
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == DEFAULT_IDENTITY
        assert identity == DEFAULT_IDENTITY

def test_load_custom_identity(tmp_path):
    target_path = tmp_path / "identity.json"
    custom_data = {
        "user_name": "Alice",
        "user_full_name": "Alice Smith",
        "user_profession": "Data Scientist",
        "user_specialty": "deep learning and NLP",
        "user_organizations": "Google DeepMind"
    }
    
    # Créer le fichier à l'avance
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(custom_data, f, indent=2, ensure_ascii=False)
        
    with patch.object(IdentityManager, 'get_identity_path', return_value=target_path):
        identity = IdentityManager.load()
        assert identity == custom_data

def test_cache_mechanism(tmp_path):
    target_path = tmp_path / "identity.json"
    with patch.object(IdentityManager, 'get_identity_path', return_value=target_path):
        # Premier chargement
        id1 = IdentityManager.load()
        
        # Modifier le fichier directement
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump({"user_name": "Bob"}, f)
            
        # Deuxième chargement - doit renvoyer la valeur en cache
        id2 = IdentityManager.load()
        assert id2["user_name"] == DEFAULT_IDENTITY["user_name"]
        
        # Effacer le cache et recharger - doit renvoyer Bob (avec complétion des autres champs)
        IdentityManager.clear_cache()
        id3 = IdentityManager.load()
        assert id3["user_name"] == "Bob"
        assert id3["user_full_name"] == DEFAULT_IDENTITY["user_full_name"]
