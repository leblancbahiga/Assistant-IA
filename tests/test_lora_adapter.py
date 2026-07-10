"""Tests pour le chargement et la configuration de l'adaptateur LoRA RAG.

V15 Phase 5 — Item 38 : LoRA-MoE adaptateur RAG (P1 #49).

Mock complet de mlx/mlx_lm/psutil au niveau sys.modules pour éviter
l'initialisation Metal GPU et les appels réels à psutil.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

# ── Mock MLX partagé (ModuleType, compatible isinstance) ──
from tests.mocks.mlx import patch_mlx, patch_mlx_lm
patch_mlx()
patch_mlx_lm()

# Ajouts spécifiques à ce fichier de test
_mock_mx = sys.modules["mlx.core"]
_mock_mx.clear_cache = MagicMock()


@pytest.fixture(autouse=True)
def _patch_psutil():
    """Patch psutil globalement pour tous les tests de cette classe."""
    with (
        patch("psutil.virtual_memory") as mock_vm,
        patch("psutil.swap_memory") as mock_swap,
        patch("psutil.Process") as mock_proc,
    ):
        mock_vm.return_value.available = 4 * 1024**3  # 4 GB free
        mock_swap.return_value.used = 0
        mock_swap.return_value.total = 8 * 1024**3
        mock_swap.return_value.percent = 0
        mock_proc.return_value.memory_info.return_value.rss = 500 * 1024**2  # 500 MB
        yield


class TestLoRAConfig:
    """Vérifie la configuration LoRA dans LocalLLM."""

    def test_init_no_adapter(self):
        """__init__ sans adaptateur = lora_adapter_path à None."""
        from src.llm_local import LocalLLM
        llm = LocalLLM()
        assert llm._lora_adapter_path is None

    def test_set_lora_adapter(self):
        """set_lora_adapter() stocke le chemin."""
        from src.llm_local import LocalLLM
        llm = LocalLLM()
        path = "models/adapters/rag"
        llm.set_lora_adapter(path)
        assert llm._lora_adapter_path == path

    def test_adapter_rechargement(self):
        """Changer le chemin puis recharger le modèle utilise le nouveau chemin."""
        from src.llm_local import LocalLLM
        llm = LocalLLM()
        llm.set_lora_adapter("models/adapters/rag/v2")
        assert llm._lora_adapter_path == "models/adapters/rag/v2"
        llm.set_lora_adapter("models/adapters/rag/v1")
        assert llm._lora_adapter_path == "models/adapters/rag/v1"

    def test_load_skips_missing_adapter(self):
        """_load_model ne plante pas si l'adaptateur n'existe pas."""
        from src.llm_local import LocalLLM

        with (
            patch("src.llm_local.load") as mock_load,
            patch("src.llm_local.load_adapters") as mock_load_adapter,
            patch("src.llm_local.Path") as mock_path,
        ):
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.__truediv__.return_value.exists.return_value = False
            mock_load.return_value = (MagicMock(), MagicMock())

            llm = LocalLLM()
            llm._lora_adapter_path = "models/adapters/rag"
            llm._load_model("test-model")
            mock_load_adapter.assert_not_called()

    def test_load_applies_existing_adapter(self):
        """_load_model charge l'adaptateur si le fichier existe."""
        from src.llm_local import LocalLLM

        with (
            patch("src.llm_local.load") as mock_load,
            patch("src.llm_local.load_adapters") as mock_load_adapters,
            patch("src.llm_local.Path") as mock_path,
        ):
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.__truediv__.return_value.exists.return_value = True
            mock_model, mock_tokenizer = MagicMock(), MagicMock()
            mock_load.return_value = (mock_model, mock_tokenizer)
            mock_load_adapters.return_value = mock_model

            llm = LocalLLM()
            llm._lora_adapter_path = "models/adapters/rag"
            llm._load_model("test-model")
            mock_load_adapters.assert_called_once_with(mock_model, "models/adapters/rag")

    def test_load_graceful_fallback(self):
        """_load_model ne plante pas si le fichier adaptateur est corrompu."""
        from src.llm_local import LocalLLM

        with (
            patch("src.llm_local.load") as mock_load,
            patch("src.llm_local.load_adapters", side_effect=Exception("corrupted")) as mock_load_adapters,
            patch("src.llm_local.Path") as mock_path,
        ):
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.__truediv__.return_value.exists.return_value = True
            mock_model, mock_tokenizer = MagicMock(), MagicMock()
            mock_load.return_value = (mock_model, mock_tokenizer)

            llm = LocalLLM()
            llm._lora_adapter_path = "models/adapters/rag"
            llm._load_model("test-model")
            assert llm._model is mock_model
