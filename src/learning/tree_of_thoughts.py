"""NURU V16 — Tree of Thoughts (Yao et al. 2023) — Mode Agentic.

Exploration arborescente de raisonnements avec validation par actions réelles.
BFS avec auto-evaluation + backtracking + outils MCP/locaux.

V16 Agentic : chaque branche peut etre validee/invalidee par une action reelle
(lecture fichier, recherche RAG, terminal) via validate_fn.
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
    tool_evidence: str = ""                # Evidence issue d'une validation outil


@dataclass
class ToTResult:
    """Resultat d'une recherche Tree of Thoughts."""
    solution: str                          # Chemin de raisonnement complet
    nodes_explored: int = 0                # Noeuds explores total
    max_depth_reached: int = 0             # Profondeur max atteinte
    final_score: float = 0.0               # Score de la solution retenue
    total_llm_calls: int = 0               # Appels LLM effectues
    total_tool_calls: int = 0              # Appels outils effectues
    duration_ms: float = 0.0               # Duree totale


# ── Prompts ToT ──────────────────────────────────────────────────────────────

THOUGHT_GENERATION_PROMPT = """Tu explores un arbre de raisonnement pour repondre a la question.

Question : {query}
Contexte disponible : {context}

Chemin de raisonnement actuel :
{current_path}

{step_instruction}

OUTILS DISPONIBLES :
{available_tools}

QUAND UTILISER UN OUTIL :
- Si tu as besoin de verifier un fait, lire un fichier, ou chercher une information
- Mentionne l'outil dans ta continuation : [OUTIL: nom_ outil(parametres)]
- Exemple : [OUTIL: read_file(path="document.pdf")]
- Si aucune verification outil n'est necessaire, ecris juste le raisonnement normal

Genere {n_branches} continuations possibles et coherentes de ce raisonnement.
Numérote-les de 1 a {n_branches}."""

THOUGHT_EVALUATION_PROMPT = """Evalue l'utilite de cette continuation de raisonnement pour repondre a la question.

Question : {query}
Raisonnement complet : {full_path}
Nouvelle continuation a evaluer : {candidate}
{tool_evidence_section}
Score de 0 a 1 :
- 1.0 = resout la question directement (valide par outil si applicable)
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


# ── Detection d'actions dans les branches ──

TOOL_PATTERNS: dict[str, re.Pattern] = {
    "read_file": re.compile(r'\[OUTIL:\s*read_file\s*\([^)]*path\s*=\s*(["\'])([^"\']+)\1'),
    "search_files": re.compile(r'\[OUTIL:\s*search_files?\s*\([^)]*query\s*=\s*(["\'])([^"\']+)\1'),
    "search_memory": re.compile(r'\[OUTIL:\s*search_memory\s*\([^)]*query\s*=\s*(["\'])([^"\']+)\1'),
    "rag_query": re.compile(r'\[OUTIL:\s*rag_query\s*\([^)]*query\s*=\s*(["\'])([^"\']+)\1'),
    "run_command": re.compile(r'\[OUTIL:\s*run_command\s*\([^)]*command\s*=\s*(["\'])([^"\']+)\1'),
}


class TreeOfThoughtsEngine:
    """Moteur Tree of Thoughts avec BFS et validation agentic.

    Usage:
        engine = TreeOfThoughtsEngine()
        result = await engine.solve(
            query=query,
            context=rag_context,
            generate_fn=async_callable,
            validate_fn=async_validation_fn,  # Optionnel : rend le ToT agentic
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
        validate_fn: Optional[Callable[[str, str, str], Awaitable[tuple[float, str]]]] = None,
        temperature: float = 0.7,
        max_depth: Optional[int] = None,
        branch_factor: Optional[int] = None,
    ) -> ToTResult:
        """Execute une recherche arborescente de raisonnement.

        Args:
            query: Question utilisateur
            context: Contexte RAG / documents
            generate_fn: Fonction asynchrone de generation LLM
            validate_fn: Optionnel. Valide une branche via outil.
                Signature : (candidate_thought, query, context) -> (score_adjustment, evidence_text)
                Retourne (-0.5..+0.3, "preuve trouvee") pour ajuster score et evaluer.
                Si None, le ToT reste purement speculatif.
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
        result.total_tool_calls = 0

        # Decrire les outils disponibles pour le prompt
        tools_desc = self._describe_tools(validate_fn is not None)

        # BFS : file de noeuds a expandre
        frontier: list[ThoughtNode] = [root]

        while frontier and result.nodes_explored < self.max_nodes_total:
            node = frontier.pop(0)

            if node.depth >= depth:
                continue

            children, calls, tool_calls = await self._expand_node(
                node=node,
                query=query,
                context=context,
                generate_fn=generate_fn,
                validate_fn=validate_fn,
                n_branches=n_branches,
                temperature=temperature,
                tools_desc=tools_desc,
            )
            result.total_llm_calls += calls
            result.total_tool_calls += tool_calls
            node.children = children

            for child in children:
                result.nodes_explored += 1
                if result.nodes_explored >= self.max_nodes_total:
                    break

                # Si score >= 0.9, solution trouvee
                if child.score >= 0.9:
                    child.is_solution = True
                    full_path = self._build_path(child)
                    solution_text = await self._generate_solution(
                        query=query, context=context,
                        reasoning_path=full_path,
                        generate_fn=generate_fn, temperature=temperature,
                    )
                    result.total_llm_calls += 1
                    result.solution = solution_text
                    result.max_depth_reached = child.depth
                    result.final_score = child.score
                    result.duration_ms = (time.time() - start) * 1000
                    logger.info(
                        f"🌳 ToT Agentic: solution trouvee en "
                        f"{result.nodes_explored} noeuds, "
                        f"{result.total_tool_calls} outils, "
                        f"score={child.score:.2f}"
                    )
                    return result

                if child.score >= self.min_score_to_expand:
                    frontier.append(child)
                    result.max_depth_reached = max(result.max_depth_reached, child.depth)

        # Aucune solution parfaite → meilleur chemin
        logger.info(
            f"🌳 ToT Agentic: frontier epuisee ({result.nodes_explored} noeuds, "
            f"{result.total_tool_calls} outils, "
            f"profondeur max {result.max_depth_reached})"
        )
        best_path = self._find_best_path(root)
        if best_path:
            full_path = self._build_path(best_path)
            solution_text = await self._generate_solution(
                query=query, context=context,
                reasoning_path=full_path,
                generate_fn=generate_fn, temperature=temperature,
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
        validate_fn: Optional[Callable[[str, str, str], Awaitable[tuple[float, str]]]],
        n_branches: int,
        temperature: float,
        tools_desc: str,
    ) -> tuple[list[ThoughtNode], int, int]:
        """Expand un noeud en generant N branches + evaluation + validation outil."""
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
            available_tools=tools_desc,
        )

        raw = await generate_fn(prompt, temperature)
        candidates = self._parse_branches(raw, n_branches)

        children: list[ThoughtNode] = []
        llm_calls = 1
        tool_calls = 0

        for cand_text in candidates:
            if not cand_text.strip():
                continue

            # ── Phase 1 : Validation outil (si detectee dans le candidat) ──
            tool_evidence = ""
            score_adjustment = 0.0
            action_detected = self._detect_tool_usage(cand_text)

            if action_detected and validate_fn:
                logger.debug(f"  🛠 ToT Agentic: validation outil pour: {cand_text[:50]}")
                try:
                    adj, evidence = await validate_fn(cand_text, query, context)
                    score_adjustment = adj
                    tool_evidence = evidence
                    tool_calls += 1
                    if adj > 0.1:
                        logger.info(f"  ✅ Branche validee (+{adj:.2f}): {evidence[:60]}")
                    elif adj < -0.1:
                        logger.info(f"  ❌ Branche invalidee ({adj:.2f}): {evidence[:60]}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Erreur validation outil: {e}")

            # ── Phase 2 : Auto-evaluation ──
            evidence_section = ""
            if tool_evidence:
                evidence_section = (
                    f"\nValidation outil :\n{tool_evidence}\n\n"
                    f"Tiens compte de cette validation pour evaluer la continuation."
                )

            eval_prompt = THOUGHT_EVALUATION_PROMPT.format(
                query=query,
                full_path=current_path or "(debut)",
                candidate=cand_text,
                tool_evidence_section=evidence_section,
            )
            eval_raw = await generate_fn(eval_prompt, 0.2)
            llm_calls += 1
            base_score = self._parse_score(eval_raw)

            # Score final = base ± ajustement outil
            final_score = max(0.0, min(1.0, base_score + score_adjustment))

            child = ThoughtNode(
                content=cand_text.strip(),
                score=final_score,
                depth=node.depth + 1,
                parent=node,
                tool_evidence=tool_evidence[:200] if tool_evidence else "",
            )
            children.append(child)

        return children, llm_calls, tool_calls

    def _parse_branches(self, raw: str, expected: int) -> list[str]:
        """Parse les branches generees (format numerote)."""
        candidates = []
        lines = raw.strip().split("\n")
        for line in lines:
            m = re.match(r'^\s*(\d+)[.)]\s+(.*)', line)
            if m:
                candidates.append(m.group(2))
            elif line.strip() and not line.strip().startswith(("##", "---", "**")):
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
        return 0.3

    def _detect_tool_usage(self, text: str) -> Optional[tuple[str, str]]:
        """Detecte si le texte mentionne un outil et retourne (nom_outil, argument)."""
        for tool_name, pattern in TOOL_PATTERNS.items():
            m = pattern.search(text)
            if m:
                return (tool_name, m.group(2))
        return None

    def _describe_tools(self, has_validate_fn: bool) -> str:
        """Decrit les outils disponibles pour le prompt de generation."""
        if not has_validate_fn:
            return "(aucun outil disponible - raisonnement purement textuel)"
        return """- read_file(path): Lit le contenu d'un fichier local
- search_files(query): Cherche des fichiers par nom/contenu
- search_memory(query): Interroge la memoire persistante
- rag_query(query): Cherche dans les documents RAG
- run_command(command): Execute une commande shell simple"""

    def _build_path(self, node: ThoughtNode) -> str:
        """Remonte l'arbre du noeud a la racine pour construire le chemin."""
        path = []
        current = node
        while current:
            if current.content:
                line = f"Etape {current.depth}: {current.content}"
                if current.tool_evidence:
                    line += f"\n   [Evidence: {current.tool_evidence[:100]}]"
                path.append(line)
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
