"""Router — Wrapper V4.5 autour de SemanticRouter avec PolicyEngine et stratégies hybrides."""
import enum
import logging
from typing import Optional
from src.semantic_router import SemanticRouter, RouterResult
from src.core.policies import PolicyEngine
from src.core.query_context import QueryContext

logger = logging.getLogger(__name__)


class HybridStrategy(enum.Enum):
    """Stratégies hybrides local+cloud inspirées d'OpenJarvis.

    LOCAL_ONLY          : tout en local (défaut V5)
    LOCAL_CLOUD_VERIFY  : Phi-4-mini répond, Groq vérifie et corrige
    CLOUD_PLAN_LOCAL    : Groq planifie les étapes, Phi-4-mini exécute
    LOCAL_RAG_CLOUD     : RAG locale récupère, Groq synthétise (Archon)
    """
    LOCAL_ONLY = "local_only"
    LOCAL_CLOUD_VERIFY = "verify"
    CLOUD_PLAN_LOCAL = "plan"
    LOCAL_RAG_CLOUD = "rag"

    @classmethod
    def from_config(cls, mode: str):
        """Parse une string config en HybridStrategy."""
        mapping = {
            "local_only": cls.LOCAL_ONLY,
            "verify": cls.LOCAL_CLOUD_VERIFY,
            "plan": cls.CLOUD_PLAN_LOCAL,
            "rag": cls.LOCAL_RAG_CLOUD,
        }
        return mapping.get(mode, cls.LOCAL_ONLY)


class Router(SemanticRouter):
    """Extension de SemanticRouter avec PolicyEngine et stratégies hybrides.

    Ajoute :
    - Intégration du PolicyEngine pour les décisions RAM-dépendantes
    - Cache TTL (hérité de SemanticRouter V4.5 Phase 0)
    - Compatibilité ascendante
    - NURU V6 : HybridStrategy pour des stratégies local+cloud fines
    """

    def __init__(self, rag_engine=None, is_online_check=None,
                 policy_engine: PolicyEngine = None,
                 hybrid_mode: str = "local_only",
                 cloud_llm=None):  # V10.1 : pour classification LLM
        super().__init__(rag_engine=rag_engine, is_online_check=is_online_check,
                        cloud_llm=cloud_llm)
        self.policy_engine = policy_engine or PolicyEngine()
        self.hybrid_strategy = HybridStrategy.from_config(hybrid_mode)

    async def route_with_context(self, ctx: QueryContext, rag_context: Optional[str] = None,
                                  rag_result=None) -> RouterResult:
        """Route en utilisant un QueryContext pour les décisions RAM-dépendantes.

        Ajoute les informations de stratégie hybride dans le résultat.
        V10 : Spotlight contourne l'escalade RAM (pas de LLM, léger).
        V10 Audit: Accepte un rag_context/rag_result pré-calculé pour éviter
        le double appel retrieve().
        """
        result = await self.route(ctx.query, rag_context=rag_context, rag_result=rag_result)

        # V10 : Spotlight ne déclenche JAMAIS l'escalade Cloud
        # (Spotlight = mdfind, pas de LLM, pas de RAM nécessaire)
        is_spotlight = result.spotlight_context != ""

        # V10 Expert fix: Spotlight bypass — si Spotlight a trouvé du contenu,
        # forcer LOCAL_ONLY quel que soit l'état RAM
        if is_spotlight and len(result.spotlight_context) > 500:
            logger.info(
                f"🔍 Spotlight bypass: {len(result.spotlight_context)} chars trouvés "
                f"→ forçage LOCAL_ONLY (pas d'escalade Cloud)"
            )
            # Ne pas changer la décision (déjà LOCAL_RAG depuis N4)
            return result
        
        # Escalade cloud si RAM trop basse (sauf si c'est du Spotlight)
        if result.decision == "LOCAL_RAG" and not is_spotlight and self.policy_engine.should_use_cloud(ctx):
            logger.info(f"↩️ Router: RAM {ctx.ram_free_mb} MB → escalation Cloud forcée")
            result.decision = "CLOUD_GROQ"
            result.reasoning += " | RAM trop basse pour local"
        elif is_spotlight:
            logger.info(f"🔍 Router: Spotlight actif → pas d'escalade RAM")

        # Stratégie hybride : enrichir le résultat
        result.hybrid_strategy = self.hybrid_strategy.value
        result.reasoning += f" | hybrid:{self.hybrid_strategy.value}"

        return result

    def set_hybrid_strategy(self, mode: str):
        """Change la stratégie hybride à la volée."""
        self.hybrid_strategy = HybridStrategy.from_config(mode)
        logger.info(f"🔄 Router: stratégie hybride → {self.hybrid_strategy.value}")


# NURU V6 : Patch RouterResult pour inclure hybrid_strategy
# (nécessaire car RouterResult est un dataclass simple)
import src.semantic_router as sr
if not hasattr(sr.RouterResult, 'hybrid_strategy'):
    sr.RouterResult.hybrid_strategy = 'local_only'
