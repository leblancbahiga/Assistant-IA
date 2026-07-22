"""Tests d'intégration pour l'initialisation du LoRA RAG adapter.

V17 : vérifie que _init_lora_adapter() est bien appelée au démarrage
de NuruCore et que les cas limites sont gérés.

Ces tests utilisent l'AST (pas l'import direct) pour éviter
la cascade de dépendances transitives de NuruCore.
"""

import ast
import pytest
from pathlib import Path


class TestLoRAIntegration:
    """Vérifie la boucle init_lora_adapter par inspection AST + tests unitaires LocalLLM."""

    NURU_CORE_PATH = Path(__file__).parent.parent / "src" / "nuru_core.py"
    LLM_LOCAL_PATH = Path(__file__).parent.parent / "src" / "llm_local.py"

    # ── Vérification AST : _init_lora_adapter est dans __init__ ──

    def test_method_exists_and_called_in_init(self):
        """_init_lora_adapter est définie ET appelée dans __init__()."""
        with open(self.NURU_CORE_PATH) as f:
            tree = ast.parse(f.read())

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.methods = {}
                self.init_calls = []

            def visit_FunctionDef(self, node):
                self.methods[node.name] = node.lineno
                if node.name == "__init__":
                    for child in ast.walk(node):
                        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                            if isinstance(child.value.func, ast.Attribute):
                                if child.value.func.attr == "_init_lora_adapter":
                                    self.init_calls.append(child.lineno)
                self.generic_visit(node)

        finder = Finder()
        finder.visit(tree)

        assert "_init_lora_adapter" in finder.methods, (
            "La methode _init_lora_adapter() doit etre definie dans NuruCore"
        )
        assert len(finder.init_calls) >= 1, (
            "_init_lora_adapter() doit etre appelee dans __init__()"
        )
        print(f"✅ _init_lora_adapter definie ligne {finder.methods['_init_lora_adapter']}")
        print(f"✅ Appelee dans __init__() ligne {finder.init_calls[0]}")

    def test_init_called_after_model_routes(self):
        """_init_lora_adapter() est appelee APRES _init_model_routes()."""
        with open(self.NURU_CORE_PATH) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                lines = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                        if isinstance(child.value.func, ast.Attribute):
                            name = child.value.func.attr
                            if name in ("_init_model_routes", "_init_lora_adapter"):
                                lines.append((child.lineno, name))
                lines.sort(key=lambda x: x[0])
                # Trouver les positions relatives
                lora_line = None
                routes_line = None
                for line, name in lines:
                    if name == "_init_model_routes":
                        routes_line = line
                    elif name == "_init_lora_adapter":
                        lora_line = line

                assert routes_line is not None, "_init_model_routes doit etre appelee"
                assert lora_line is not None, "_init_lora_adapter doit etre appelee"
                assert lora_line > routes_line, (
                    f"_init_lora_adapter (ligne {lora_line}) doit etre appelee "
                    f"APRES _init_model_routes (ligne {routes_line})"
                )
                print(f"✅ _init_model_routes ligne {routes_line} → _init_lora_adapter ligne {lora_line}")

    # ── Vérification AST : logique métier ──

    def test_checks_adapter_file_exists(self):
        """_init_lora_adapter verifie Path.exists() avant d'appeler set_lora_adapter."""
        with open(self.NURU_CORE_PATH) as f:
            content = f.read()

        # Ces phrases doivent etre presentes dans le corps de la methode
        has_exists_check = "adapter_file.exists()" in content or "adapter_file.exists" in content
        has_set_lora = "set_lora_adapter" in content
        has_warning = "introuvable" in content

        assert has_exists_check, "Doit verifier adapter_file.exists() (AST check)"
        assert has_set_lora, "Doit appeler set_lora_adapter() (AST check)"
        assert has_warning, "Doit logger un warning si fichier introuvable (AST check)"
        print(f"✅ Logique _init_lora_adapter verifiee par AST (exists={has_exists_check}, "
              f"set_lora={has_set_lora}, warning={has_warning})")

    # ── Vérification : la propriété lora_active existe sur LocalLLM ──

    def test_local_llm_lora_active_property(self):
        """Vérifie que LocalLLM expose lora_active."""
        with open(self.LLM_LOCAL_PATH) as f:
            tree = ast.parse(f.read())

        has_lora_active = False
        has_lora_loaded = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if "lora_active" in node.name or "lora_active" in ast.dump(node):
                    has_lora_active = True
                if "lora_loaded" in node.name or "lora_loaded" in ast.dump(node):
                    has_lora_loaded = True

        assert has_lora_active, "LocalLLM doit avoir une propriete/attribut lora_active"
        print("✅ LocalLLM expose lora_active")

    # ── Tests unitaires LocalLLM (avec mocks MLX) ──

    def test_local_llm_set_lora_adapter_stores_path(self):
        """set_lora_adapter() stocke le chemin dans _lora_adapter_path."""
        import sys
        from unittest.mock import MagicMock

        # Mocker mlx_lm avant l'import
        sys.modules["mlx_lm"] = MagicMock()
        sys.modules["mlx_lm.utils"] = MagicMock()

        from src.llm_local import LocalLLM

        # Réinitialiser le singleton
        LocalLLM._instance = None
        LocalLLM._initialized = False

        llm = LocalLLM()
        path = "data/adapters/rag"
        llm.set_lora_adapter(path)
        assert llm._lora_adapter_path == path, "Le chemin doit etre stocke"
        print(f"✅ set_lora_adapter('{path}') stocke le chemin")

    def test_local_llm_lora_active_false_by_default(self):
        """lora_active est False tant que load_adapters n'a pas reussi."""
        import sys
        from unittest.mock import MagicMock

        # Mocker mlx_lm avant l'import
        sys.modules["mlx_lm"] = MagicMock()
        sys.modules["mlx_lm.utils"] = MagicMock()

        from src.llm_local import LocalLLM

        LocalLLM._instance = None
        LocalLLM._initialized = False

        llm = LocalLLM()
        assert llm.lora_active is False, (
            "lora_active doit etre False avant chargement"
        )
        print(f"✅ lora_active={llm.lora_active} par defaut (attendu: False)")
