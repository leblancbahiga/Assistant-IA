"""NURU V16 — Tree of Thoughts (Yao et al. 2023).

Exploration arborescente de raisonnements pour les goals P0 critiques.
BFS avec auto-evaluation + backtracking. Cout eleve (5-10x LLM calls),
reserve aux taches de planification et diagnostic multi-saut.

Limite M1 8Go : generation SEQUENTIELLE (pas parallele), profondeur 3 max.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ThoughtNode:
    """Noeud de l'arbre de raisonnement."""
    content: str                           # Texte du raisonnement a ce noeud
    score: float = 0.0                     # Auto-evaluation (0..1)
    depth: int = 0                         # Profondeur dans l'arbre
    parent: Optional['ThoughtNode'] = None # Noeud parent
    children: list['ThoughtNode'] = field(default_factory=list)
    is_solution: bool = False              # Marque si mene a une solution complete


@dataclass
class ToTResult:
    """Resultat d'une recherche Tree of Thoughts."""
    solution: str                          # Chemin de raisonnement complet
    nodes_explored: int = 0                # Noeuds explores total
    max_depth_reached: int = 0             # Profondeur max atteinte
    final_score: float = 0.0               # Score de la solution retenue
    total_llm_calls: int = 0               # Appels LLM effectues
    duration_ms: float = 0.0               # Duree totale


# ── Prompts ToT ──────────────────────────────────────────────────────────────

THOUGHT_GENERATION_PROMPT = """Tu explores un arbre de raisonnement pour repondre a la question.

Question : {query}
Contexte disponible : {context}

Chemin de raisonnement actuel :
{current_path}

{step_instruction}

Genere {n_branches} continuations possibles et coherentes de ce raisonnement.
Numérote-les de 1 a {n_branches}. Chaque continuation doit faire avancer le raisonnement d'un pas logique.

FORMAT :
1. [continuation 1]
2. [continuation 2]
..."""

THOUGHT_EVALUATION_PROMPT = """Evalue l'utilite de cette continuation de raisonnement pour repondre a la question.

Question : {query}
Raisonnement complet : {full_path}
Nouvelle continuation a evaluer : {candidate}

Score de 0 a 1 :
- 1.0 = resout la question directement
- 0.7 = fait progresser significativement
- 0.4 = avance modere
- 0.1 = hors sujet ou boucle
- 0.0 = inutilisable

Reponds UNIQUEMENT par le nombre (ex: 0.7)."""

SOLUTION_GENERATION_PROMPT = """Question : {query}
Contexte : {context}

Voici le chemin de raisonnement que tu as parcouru :
{reasoning_path}

Formule maintenant la reponse finale complete et directe a la question.
Utilise le chemin de raisonnement ci-dessus pour assurer l'exactitude,
mais donne une reponse autonome (qui se tient sans le raisonnement)."""


class TreeOfThoughtsEngine:
    """Moteur Tree of Thoughts avec BFS.

    Usage:
        engine = TreeOfThoughtsEngine()
        result = await engine.solve(
            query=query,
            context=rag_context,
            generate_fn=async_callable,
            max_depth=3,
            branch_factor=2,
        )
    """

    def __init__(
        self,
        max_depth: int = 3,
        branch_factor: int = 2,
        min_score_to_expand: float = 0.3,
        max_nodes_total: int = 20,
    ):
        self.max_depth = max_depth
        self.branch_factor = branch_factor
        self.min_score_to_expand = min_score_to_expand
        self.max_nodes_total = max_nodes_total

    async def solve(
        self,
        query: str,
        context: str,
        generate_fn: Callable[[str, float], Awaitable[str]],
        temperature: float = 0.7,
        max_depth: Optional[int] = None,
        branch_factor: Optional[int] = None,
    ) -> ToTResult:
        """Execute une recherche arborescente de raisonnement.

        Args:
            query: Question utilisateur
            context: Contexte RAG / documents
            generate_fn: Fonction asynchrone de generation LLM
            temperature: Temperature pour la generation
            max_depth: Profondeur max de l'arbre
            branch_factor: Nombre de branches par noeud

        Returns:
            ToTResult avec la solution et les metriques
        """
        start = time.time()
        depth = max_depth or self.max_depth
        n_branches = branch_factor or self.branch_factor

        root = ThoughtNode(content="", depth=0)
        result = ToTResult(nodes_explored=1)
        result.total_llm_calls = 0

        # BFS : file de noeuds a expandre
        frontier: list[ThoughtNode] = [root]

        while frontier and result.nodes_explored < self.max_nodes_total:
            node = frontier.pop(0)

            # Ne pas expandre au-dela de la profondeur max
            if node.depth >= depth:
                continue

            # Generer les branches filles
            children, calls = await self._expand_node(
                node=node,
                query=query,
                context=context,
                generate_fn=generate_fn,
                n_branches=n_branches,
                temperature=temperature,
            )
            result.total_llm_calls += calls
            node.children = children

            for child in children:
                result.nodes_explored += 1
                if result.nodes_explored >= self.max_nodes_total:
                    break

                # Si score excellent, marquer comme solution et arreter
                if child.score >= 0.9:
                    child.is_solution = True
                    full_path = self._build_path(child)
                    solution_text = await self._generate_solution(
                        query=query,
                        context=context,
                        reasoning_path=full_path,
                        generate_fn=generate_fn,
                        temperature=temperature,
                    )
                    result.total_llm_calls += 1
                    result.solution = solution_text
                    result.max_depth_reached = child.depth
                    result.final_score = child.score
                    result.duration_ms = (time.time() - start) * 1000
                    logger.info(
                        f"🌳 ToT: solution trouvee en {result.nodes_explored} "
                        f"noeuds, score={child.score:.2f}"
                    )
                    return result

                # Ajouter a la frontier si assez bon
                if child.score >= self.min_score_to_expand:
                    frontier.append(child)
                    result.max_depth_reached = max(result.max_depth_reached, child.depth)

        # Aucune solution parfaite trouvee → prendre le meilleur chemin
        logger.info(
            f"🌳 ToT: frontier epuisee ({result.nodes_explored} noeuds, "
            f"profondeur max {result.max_depth_reached})"
        )
        best_path = self._find_best_path(root)
        if best_path:
            full_path = self._build_path(best_path)
            solution_text = await self._generate_solution(
                query=query,
                context=context,
                reasoning_path=full_path,
                generate_fn=generate_fn,
                temperature=temperature,
            )
            result.total_llm_calls += 1
            result.solution = solution_text
            result.final_score = best_path.score
        else:
            result.solution = "[ToT] Aucune solution trouvee."

        result.duration_ms = (time.time() - start) * 1000
        return result

    async def _expand_node(
        self,
        node: ThoughtNode,
        query: str,
        context: str,
        generate_fn: Callable[[str, float], Awaitable[str]],
        n_branches: int,
        temperature: float,
    ) -> tuple[list[ThoughtNode], int]:
        """Expand un noeud en generant N branches + evaluation."""
        current_path = self._build_path(node)
        if not current_path:
            step_instruction = "Propose les premieres pistes de raisonnement."
        else:
            step_instruction = f"Continue le raisonnement a partir de l'etape {node.depth}."

        prompt = THOUGHT_GENERATION_PROMPT.format(
            query=query,
            context=context,
            current_path=current_path or "(debut)",
            step_instruction=step_instruction,
            n_branches=n_branches,
        )

        raw = await generate_fn(prompt, temperature)
        candidates = self._parse_branches(raw, n_branches)

        children: list[ThoughtNode] = []
        llm_calls = 1  # generation

        for cand_text in candidates:
            if not cand_text.strip():
                continue

            # Auto-evaluation de la branche
            eval_prompt = THOUGHT_EVALUATION_PROMPT.format(
                query=query,
                full_path=current_path or "(debut)",
                candidate=cand_text,
            )
            eval_raw = await generate_fn(eval_prompt, 0.2)  # temperature basse pour evaluation stable
            llm_calls += 1
            score = self._parse_score(eval_raw)

            child = ThoughtNode(
                content=cand_text.strip(),
                score=score,
                depth=node.depth + 1,
                parent=node,
            )
            children.append(child)

        return children, llm_calls

    def _parse_branches(self, raw: str, expected: int) -> list[str]:
        """Parse les branches generees (format numerote)."""
        candidates = []
        lines = raw.strip().split("\n")
        for line in lines:
            m = re.match(r'^\s*(\d+)[.)]\s+(.*)', line)
            if m:
                candidates.append(m.group(2))
            elif line.strip() and not line.strip().startswith(("##", "---", "**")):
                # Fallback : ligne non vide sans format numerote
                candidates.append(line.strip())
            if len(candidates) >= expected:
                break
        return candidates

    def _parse_score(self, raw: str) -> float:
        """Parse un score numerique depuis la reponse d'evaluation."""
        m = re.search(r'(\d+\.?\d*)', raw.strip())
        if m:
            try:
                val = float(m.group(1))
                return max(0.0, min(1.0, val))
            except ValueError:
                pass
        return 0.3  # score par defaut si parsing echoue

    def _build_path(self, node: ThoughtNode) -> str:
        """Remonte l'arbre du noeud a la racine pour construire le chemin."""
        path = []
        current = node
        while current:
            if current.content:
                path.append(f"Etape {current.depth}: {current.content}")
            current = current.parent
        return "\n".join(reversed(path))

    def _find_best_path(self, root: ThoughtNode) -> Optional[ThoughtNode]:
        """Trouve le meilleur chemin feuille par score cumule."""
        best_score = -1.0
        best_node = None

        def dfs(node: ThoughtNode, cumulative: float):
            nonlocal best_score, best_node
            if not node.children:
                if node.depth > 0 and node.score > best_score:
                    best_score = node.score
                    best_node = node
                return
            for child in node.children:
                dfs(child, cumulative + child.score)

        dfs(root, 0.0)
        return best_node

    async def _generate_solution(
        self,
        query: str,
        context: str,
        reasoning_path: str,
        generate_fn: Callable[[str, float], Awaitable[str]],
        temperature: float,
    ) -> str:
        """Genere la reponse finale a partir du chemin de raisonnement."""
        prompt = SOLUTION_GENERATION_PROMPT.format(
            query=query,
            context=context,
            reasoning_path=reasoning_path,
        )
        return await generate_fn(prompt, min(temperature, 0.5))
