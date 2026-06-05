"""Router — Wrapper V4.5 autour de SemanticRouter avec PolicyEngine."""
import logging
from src.semantic_router import SemanticRouter, RouterResult
from src.core.policies import PolicyEngine
from src.core.query_context import QueryContext

logger = logging.getLogger(__name__)


class Router(SemanticRouter):
    """Extension de SemanticRouter avec PolicyEngine.

    Ajoute :
    - Intégration du PolicyEngine pour les décisions RAM-dépendantes
    - Cache TTL (hérité de SemanticRouter V4.5 Phase 0)
    - Compatibilité ascendante : se comporte exactement comme SemanticRouter
    """

    def __init__(self, rag_engine=None, is_online_check=None,
                 policy_engine: PolicyEngine = None):
        super().__init__(rag_engine=rag_engine, is_online_check=is_online_check)
        self.policy_engine = policy_engine or PolicyEngine()

    async def route_with_context(self, ctx: QueryContext) -> RouterResult:
        """Route en utilisant un QueryContext pour les décisions RAM-dépendantes.

        Utilise le PolicyEngine pour affiner la décision si RAM basse.
        """
        result = await self.route(ctx.query)
        if result.decision == "LOCAL_RAG" and self.policy_engine.should_use_cloud(ctx):
            logger.info(f"↩️ Router: RAM {ctx.ram_free_mb} MB → escalation Cloud forcée")
            result.decision = "CLOUD_GROQ"
            result.reasoning += " | RAM trop basse pour local"
        return result
