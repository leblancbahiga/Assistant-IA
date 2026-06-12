#!/usr/bin/env python3
"""
Script d'analyse statique NURU V10 — Compte les lignes, les fonctions,
les classes, et détecte les patterns problématiques dans chaque module.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

MODULES = {
    "RAG Engine": "src/rag_engine.py",
    "Multi Search": "src/rag/multi_search.py",
    "Retrieval": "src/rag/retrieval.py",
    "Orchestrator": "src/core/orchestrator.py",
    "Router": "src/core/router.py",
    "Semantic Router": "src/semantic_router.py",
    "Embedder": "src/embedder.py",
    "LLM Cloud": "src/llm_cloud.py",
    "LLM Local": "src/llm_local.py",
    "Config": "src/config.py",
    "Query Rewriter": "src/rag/query_rewriter.py",
    "Spotlight": "src/rag/spotlight.py",
    "Dashboard": "src/ui/dashboard.py",
    "Fact Checker": "src/rag/fact_checker.py",
    "Token Juice": "src/token_juice.py",
    "Nuru Core": "src/nuru_core.py",
}

def analyze_file(path):
    p = Path(path)
    if not p.exists():
        return {"error": f"Fichier introuvable: {path}"}
    
    with open(p) as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"Erreur syntaxe: {e}"}
    
    classes = []
    functions = []
    async_funcs = []
    todos = []
    except_bare = 0
    except_pass = 0
    returns_none_count = 0
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
            if any(d for d in node.decorator_list if isinstance(d, ast.Name) and d.id in ('coroutine', 'async')):
                async_funcs.append(node.name)
        # Chercher les commentaires TODO/FIXME/HACK
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for kw in ['TODO', 'FIXME', 'HACK', 'XXX']:
                if kw in node.value.value:
                    todos.append(f"Ligne {node.lineno}: {node.value.value.strip()[:100]}")
    
    # Compter les except Exception: (sans log)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.name is None:
                except_bare += 1
            elif isinstance(node.body[-1], ast.Raise):
                pass  # re-raise OK
            elif all(isinstance(s, (ast.Pass, ast.Continue, ast.Break)) for s in node.body):
                except_pass += 1
    
    lines = source.count('\n')
    
    return {
        "lines": lines,
        "classes": len(classes),
        "functions": len(functions),
        "async_functions": len(async_funcs),
        "todos": todos[:5],
        "except_bare": except_bare,
        "except_pass": except_pass,
        "class_names": classes[:10],
        "func_names": functions[:15],
    }

print("=" * 70)
print("AUDIT STATIQUE NURU V10 — Analyse des modules")
print("=" * 70)
print()

total_lines = 0
for name, path in MODULES.items():
    result = analyze_file(path)
    if "error" in result:
        print(f"❌ {name:25s} | {path:40s} | ERREUR: {result['error']}")
        continue
    total_lines += result["lines"]
    
    flags = []
    if result["except_bare"] > 0:
        flags.append(f"⚠️ {result['except_bare']}x bare except")
    if result["except_pass"] > 0:
        flags.append(f"⚠️ {result['except_pass']}x silent pass")
    if result["todos"]:
        flags.append(f"📝 {len(result['todos'])} TODOs")
    
    flag_str = " | ".join(flags) if flags else "✅"
    print(f"  {name:25s} | {result['lines']:5d} lignes | {result['classes']} classes, {result['functions']} fns ({result['async_functions']} async) | {flag_str}")

print()
print(f"📊 TOTAL: {total_lines} lignes dans {len(MODULES)} modules")
print("=" * 70)
