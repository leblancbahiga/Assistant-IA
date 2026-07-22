import asyncio
import logging
import os
import time
from pathlib import Path
# V16 AUDIT FIX QW20 : Lock import supprimé (inutilisé)
from typing import Any, AsyncGenerator, Awaitable, Optional
from src.config import config
from src.rag_engine import RAGEngine
from src.routing import Router
from src.llm_local import LocalLLM
from src.llm_cloud import CloudLLM
from src.memory_store import MemoryStore
from src.audio import AudioEngine
from src.cloud import WebSearch
from src.context_manager import ContextBudget
from src.runtime_manager import RuntimeManager
from src.core.events import EventBus
# V10.3 : PluginSystem et ReflectionEngine supprimés (stubs YAGNI).
from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS
from src.ram_monitor import RAMMonitor  # Monitoring RAM
from src.document_watcher import DocumentWatcher  # Auto-indexation watchdog
from src.core.orchestrator import NuruOrchestrator  # Orchestrateur principal
from src.core.policies import PolicyEngine  # Moteur de politiques
from src.extraction import PostSessionExtractor  # Extraction post-session
from src.long_term_memory import LongTermMemory  # V10.1 : Mémoire long terme
from src.memory_bridge import MemoryBridge  # V10.1 : Pont V5+V9

# Phase 3 : Proactif, Connaissances, Cycle de sommeil
from src.knowledge.graph import KnowledgeGraph
from src.memory.sleep_cycle import SleepCycleManager
from src.memory.dynamic_prompt import DynamicPromptBuilder, PromptContext
from src.proactive.engine import ProactiveEngine
from src.proactive.routines import RoutineScheduler, RoutinePreset
from src.personality.engine import PersonaEngine

# Phase 4 : MCP, ModelRouter, CostGuard
from src.models.cost_guard import CostGuard, CostConfig
from src.models.router import ModelRouter, ModelRoute, TaskType, RoutingDecision
from src.mcp.server import MCPServer, MCPTool
from src.mcp.client import MCPClient

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """
Tu es NURU V8+, l'assistant IA personnel de {user_name}.

Ton utilisateur : {user_full_name} — {user_profession}, spécialiste de {user_specialty} ({user_organizations}).

Ta mission principale est de fournir des réponses exactes, traçables, utiles et adaptées au contexte disponible.

# CONNAISSANCES GÉNÉRALES
Tu possèdes des connaissances larges en mathématiques, logique, sciences, histoire, 
géographie, technologie, et sujets divers. Tu peux répondre à ces questions directement
sans chercher dans les documents. Ne dis JAMAIS "je ne trouve pas dans vos documents"
pour une question de culture générale, un calcul, un puzzle, ou une question factuelle
générale.

# PRIORITÉ DES SOURCES
Lorsque des documents sont fournis via le système RAG :
1. Les documents utilisateur sont prioritaires.
2. Les informations doivent être recherchées en priorité dans ces documents.
3. Si plusieurs documents sont disponibles, croise les informations avant de répondre.
4. Si les documents ne contiennent PAS la réponse, utilise tes connaissances générales
   et indique clairement que la réponse vient de tes connaissances, pas des documents.

# MODE RAG STRICT
Lorsque la question porte explicitement sur les documents fournis (nom de fichier, 
projet spécifique, données personnelles) :
- Utilise uniquement les informations présentes dans les sources.
- N'invente jamais une information absente.
- Cite systématiquement la source utilisée.
- Si l'information n'existe pas dans les documents, réponds :
  "Je ne trouve pas cette information dans les documents fournis. Mais voici ce que je sais personnellement : [réponse de tes connaissances]."

# MODE HYBRIDE
Lorsque les documents ne contiennent qu'une partie de la réponse :
- Commence par exploiter les documents.
- Complète avec des connaissances générales clairement identifiées comme telles.
- Sépare les deux sections.

# GESTION DES CONFLITS
Si plusieurs documents contiennent des informations contradictoires :
- Signale explicitement la contradiction.
- Cite chaque source concernée.
- Ne choisis pas arbitrairement une version.

# TRAÇABILITÉ
Chaque donnée factuelle importante doit être accompagnée de sa source.
Exemple : Le biochar a amélioré les rendements de 18 % [Rapport Agro 2024, p. 15].

# GESTION DE L'INCERTITUDE
Si le contexte est insuffisant :
- Indique que les informations disponibles ne permettent pas de conclure.
- Ne complète jamais par des suppositions.

# FORMAT DE SORTIE
Utilise Markdown. Selon le contexte, privilégie : titres, listes, tableaux, encadrés, citations.

# STYLE
Précis, factuel, professionnel, direct, sans phrases de remplissage.

# OBJECTIF PRINCIPAL
Privilégier l'exactitude des informations avant la fluidité du discours.
Privilégier les preuves avant les suppositions.
Privilégier les sources avant les connaissances mémorisées.
""".strip()

class NuruCore:
    """Orchestrateur asynchrone principal de NURU V8+.

    Coordonne le pipeline : routing, RAG, LLM local/cloud,
    mémoire, audio, extraction. Délègue à NuruOrchestrator
    pour la boucle de traitement principale.
    """

    def __init__(self):
        self.cloud_llm = CloudLLM()  # V10.1 : déplacé AVANT le router pour classification
        # V16 AUDIT FIX QW1 : injecter cloud_llm existant dans RAGEngine (-40 Mo RAM)
        self.rag = RAGEngine(cloud_llm=self.cloud_llm)
        self.router = Router(rag_engine=self.rag, is_online_check=self._is_online,  # V17 Phase 2 : async
                            cloud_llm=self.cloud_llm)
        self.web = WebSearch()
        self.local_llm = LocalLLM()
        self.memory = MemoryStore()
        self.audio = AudioEngine()
        self.context_budget = ContextBudget(
            max_prompt_tokens=8192, # V10.2: 32K pour Phi-4-mini (était 4096)
            reserved_response=2048  # V10.2: réponses plus longues (était 1024)
        )
        self.runtime = RuntimeManager()
        self.event_bus = EventBus()
        # V10.3 — AUDIT Arch-01 : self.plugins et self.reflection supprimés (stubs YAGNI)
        self.ingestion = IngestionEngine(rag_engine=self.rag)  # V16 FIX: partage le RAGEngine
        
        # V4 : Monitoring RAM actif
        # V10.3k — audit Option C : seuils lus depuis Config (surchargeables via YAML/env)
        self.ram_monitor = RAMMonitor(
            warning_threshold_gb=getattr(config, "ram_warning_threshold_gb", 1.0),
            critical_threshold_gb=getattr(config, "ram_critical_threshold_gb", 0.5),
        )
        # Connecte le déchargement du reranker au RAMMonitor
        self.ram_monitor.register_callback(self.rag.clear_reranker)
        # V17 Phase 2 : déchargement conditionnel de l'embedder si swap > 50%
        self.ram_monitor.register_callback(self._maybe_unload_embedder)
        # NOTE : ram_monitor.start() déplacé dans start_background_tasks()
        # car il nécessite une boucle asyncio en cours d'exécution.

        # V4.5 : Orchestrateur pipeline (utilise les mêmes composants)
        self.orchestrator = NuruOrchestrator(
            router=self.router,
            rag_engine=self.rag,
            local_llm=self.local_llm,
            cloud_llm=self.cloud_llm,
            memory_store=self.memory,
            policy_engine=PolicyEngine(),
            event_bus=self.event_bus,
            runtime_manager=self.runtime,
            web_search=self.web,
            context_budget=self.context_budget,
            system_prompt_builder=self.build_system_prompt,  # Callback prompt système
        )
        logger.info("🚀 NuruOrchestrator V4.5 initialisé")

        # V10.1 : MemoryBridge — connecte V5 + V9 au pipeline
        v9_db = str(Path.home() / ".nuru" / "memory_v9.db")
        self._bridge = MemoryBridge(v5_memory_store=self.memory, v9_db_path=v9_db)
        self._ltm = LongTermMemory(self._bridge)
        self.orchestrator.set_long_term_memory(self._ltm)
        logger.info("🧠 MemoryBridge + Long-Term Memory câblées")

        # V4.5 : Extracteur post-session (profil utilisateur)
        self._extractor = PostSessionExtractor()

        # V10.3k — AUDIT BUG-FIX B-Task-Destroyed : ensemble des background tasks.
        # Sans garde, asyncio crée la task → pas de référence → garbage collection
        # à la fermeture de la loop → ERROR "Task was destroyed but it is pending!"
        # seen in user logs at every query termination.
        # Le bookkeeping : self._bg_tasks.add(t) (garde la ref) + add_done_callback(discard)
        # nettoie automatiquement quand la task finit.
        self._bg_tasks: set = set()
        self._indexing_enabled = True  # V12 : flag pour stopper l'indexation

        # ── Phase 3 : Knowledge Graph ──
        self.knowledge_graph = KnowledgeGraph()
        self.knowledge_graph.init()

        # ── Phase 3 : Sleep Cycle ──
        self.sleep_cycle = SleepCycleManager()

        # ── Phase 3 : Proactive Engine ──
        self.proactive = ProactiveEngine()
        self._register_proactive_collectors()

        # ── Phase 3 : Dynamic Prompt Builder ──
        self.prompt_builder = DynamicPromptBuilder(
            persona=PersonaEngine(),
            knowledge=self.knowledge_graph,
        )

        # ── Phase 3 : Routine Scheduler ──
        self.routines = RoutineScheduler()
        self.routines.load_preset(RoutinePreset.default())

        # ── Phase 4 : CostGuard ──
        daily_budget = getattr(config, "cost_daily_budget", getattr(config, "daily_api_budget", 0.50))
        monthly_budget = getattr(config, "cost_monthly_budget", getattr(config, "monthly_api_budget", 10.0))
        self.cost_guard = CostGuard(CostConfig(
            daily_budget=daily_budget,
            monthly_budget=monthly_budget,
        ))
        logger.info(f"💰 CostGuard: ${daily_budget}/jour, ${monthly_budget}/mois")

        # ── Phase 4 : ModelRouter ──
        self.model_router = ModelRouter(cost_guard=self.cost_guard)
        self._init_model_routes()

        # ── Connecter ModelRouter + CostGuard à CloudLLM ──
        self.cloud_llm.model_router = self.model_router
        self.cloud_llm.cost_guard = self.cost_guard
        logger.info("🔗 CloudLLM connecté à ModelRouter + CostGuard")

        # ── Phase 4 : MCP ──
        self.mcp_server = MCPServer(name="nuru-mcp", version="12.0.0")
        self.mcp_client = MCPClient()
        self._register_mcp_tools()
        self._online_cache: tuple[float, bool] = (0.0, False)  # TTL timestamp + cached value

    async def _is_online(self) -> bool:
        """Vérifie si un fournisseur Cloud est accessible (async, parallel, cache TTL).

        Cache : 30s entre les vérifications (les appels consécutifs retournent la
        valeur en cache sans toucher au réseau). Teste TOUS les hosts en parallèle
        avec timeout 0.5s. V17 Phase 2.
        """
        now = time.monotonic()
        # Cache TTL : 30 secondes
        if now - self._online_cache[0] < 30.0:
            return self._online_cache[1]

        import socket
        hosts = [
            "api.groq.com", "openrouter.ai", "api.deepseek.com",
            "opencode.ai", "dashscope.aliyuncs.com", "api.openai.com",
            "generativelanguage.googleapis.com", "api.together.xyz",
            "api.mistral.ai", "api.x.ai", "integrate.api.nvidia.com",
        ]

        async def _try_host(host: str) -> bool:
            try:
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: socket.create_connection((host, 443), timeout=0.5),
                    ),
                    timeout=0.5,
                )
                return True
            except Exception:
                return False

        results = await asyncio.gather(*[_try_host(h) for h in hosts])
        online = any(results)
        self._online_cache = (now, online)
        return online

    def _is_online_sync(self) -> bool:
        """Version synchrone de _is_online pour les contextes sans event loop.

        Ne fait PAS de cache TTL (pour cohérence avec le cache de la version async).
        Timeout total : 0.5s par host, max 11 hosts.
        Note: utiliser la version async dans le pipeline principal.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # On est dans un event loop running → forcer le cache
                return self._online_cache[1] if self._online_cache[0] > 0 else False
        except RuntimeError:
            pass
        # Pas de loop → test synchrone séquentiel (fallback startup uniquement)
        import socket
        hosts = [
            ("api.groq.com", 443), ("openrouter.ai", 443), ("api.deepseek.com", 443),
            ("opencode.ai", 443), ("dashscope.aliyuncs.com", 443), ("api.openai.com", 443),
            ("generativelanguage.googleapis.com", 443), ("api.together.xyz", 443),
            ("api.mistral.ai", 443), ("api.x.ai", 443),
            ("integrate.api.nvidia.com", 443),
        ]
        for host, port in hosts:
            try:
                socket.create_connection((host, port), timeout=0.5)
                self._online_cache = (time.monotonic(), True)
                return True
            except (socket.timeout, OSError):
                continue
        self._online_cache = (time.monotonic(), False)
        return False

    def _check_cloud_online(self) -> Awaitable[bool]:
        """Transition vers la nouvelle _is_online. Appelé par les anciens callers."""
        return self._is_online()

    async def _maybe_unload_embedder(self, force: bool = False) -> None:
        """Callback RAMMonitor : décharge l'embedder MLX si swap > 50%.

        L'embedder (~400-500 Mo) est rechargé automatiquement par _load_model()
        au prochain appel embed()/embed_sync(). V17 Phase 2.
        """
        try:
            from src.core.ram_budget import get_budget
            budget = get_budget()
            state = budget.probe()
            should_unload = force or state.swap_percent > 50 or state.free_ram_gb < 1.5
        except Exception:
            import psutil
            swap = psutil.swap_memory()
            mem = psutil.virtual_memory()
            swap_pct = swap.percent if swap.total > 0 else 0
            free_ram_gb = mem.available / (1024**3)
            should_unload = force or swap_pct > 50 or free_ram_gb < 1.5

        if not should_unload:
            return

        from src.embedder import Embedder
        embedder = Embedder()
        if embedder._model is not None:
            embedder.unload()
            logger.info("🧹 Embedder déchargé (RAMMonitor) — libère ~400 Mo")

    def start_background_tasks(self):
        """Lance les tâches asynchrones et le watcher en arrière-plan.
        
        V17 : Auto-indexation startup désactivée (trop de RAM sur M1 8 Go).
        L'indexation est maintenant manuelle via les Préférences.
        Le watcher temps réel continue pour les fichiers modifiés.
        """
        # V16 FIX : RAMMonitor.start() ici (dans le thread asyncio) plutôt que dans __init__
        self.ram_monitor.start()
        
        # V17 : Auto-indexation startup retirée — saturation RAM sur M1 8 Go
        # asyncio.create_task(self._auto_index_with_ram_guard()).add_done_callback(...)
        
        # V4.5 : Document watcher (watchdog) pour auto-indexation temps réel
        self._watcher = DocumentWatcher(index_callback=self.ingestion.index_file)
        self._watcher.start()
        logger.info("📁 Document watcher démarré (surveille Documents, Desktop, Downloads)")

        # S'abonne à l'événement index_reset pour stopper l'indexation
        from src.core.events import EventBus
        EventBus().subscribe("index_reset", self._on_index_reset)

        # V17 FIX : api_keys_updated → rebuild les routes ModelRouter
        EventBus().subscribe("api_keys_updated", lambda _: self.refresh_model_routes())

        # ── Phase 3 : Sleep cycle monitoring ──
        self.sleep_cycle.start_monitoring()
        task = asyncio.create_task(self._sleep_cycle_loop())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

        # ── Phase 3 : Proactive signal collection ──
        task = asyncio.create_task(self._proactive_collect_loop())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

        # ── Phase 4 : MCP HTTP Server ──
        task = asyncio.create_task(self.mcp_server.start_http(port=8765))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

        # ── Phase 5 : Purge automatique historique + cache ──
        task = asyncio.create_task(self._auto_purge_loop())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _auto_purge_loop(self) -> None:
        """Purge périodique de l'historique et du cache (toutes les 2h).
        V16 FIX : Évite l'accumulation mémoire sur longues sessions.
        """
        while True:
            try:
                await asyncio.sleep(7200)  # Toutes les 2 heures
                # Purger l'historien : garder les 50 derniers messages
                try:
                    self.memory.purge_history(keep_last=50)
                    logger.info("🧹 Purge auto : historique réduit à 50 messages")
                except Exception as e:
                    logger.debug(f"Purge history: {e}")

                # Purger le cache sémantique : supprimer les entrées à 0 hit
                try:
                    from src.core.ram_budget import get_budget
                    probe = get_budget().probe()
                    if probe.swap_percent > 50:
                        self.memory.purge_cache()
                        logger.info("🧹 Purge auto : cache sémantique vidé (swap élevé)")
                except Exception as e:
                    logger.debug(f"Purge cache: {e}")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erreur dans _auto_purge_loop")

    async def _on_index_reset(self, _data=None):
        """Callback quand l'utilisateur vide l'index depuis l'UI."""
        logger.info("🛑 Index vidé par l'utilisateur — arrêt de l'auto-indexation")
        await self.stop_indexing()

    async def stop_indexing(self) -> None:
        """Stoppe l'auto-indexation périodique et le watcher temps réel."""
        self._indexing_enabled = False
        if hasattr(self, '_watcher') and self._watcher:
            self._watcher.stop()
        logger.info("🛑 Auto-indexation arrêtée — utiliser reset_index() pour réactiver")

    async def start_indexing(self, directories: Optional[list[Path]] = None) -> int:
        """Lance une indexation manuelle (un seul cycle) sur les dossiers spécifiés.
        
        V17: Pour déclenchement depuis les Préférences — pas de boucle,
        pas de sleep initial, RAM guard conservée.
        Retourne le nombre de fichiers indexés.
        """
        if not self._indexing_enabled:
            self._indexing_enabled = True
        
        dirs = directories or [
            Path.home() / "Documents",
            Path.home() / "Desktop", 
            Path.home() / "Downloads",
        ]
        # Exécute la logique de _auto_index_with_ram_guard en one-shot
        count = await self._run_index_cycle(dirs)
        return count

    async def _run_index_cycle(self, dirs_to_index: list[Path]) -> int:
        """Exécute un cycle d'indexation one-shot avec RAM guard.

        V17: extrait de _auto_index_with_ram_guard pour réutilisable
        en manuel (start_indexing) ou automatique.
        Retourne le nombre de fichiers indexés.
        """
        EXCLUDED_DIRS = {
            ".git", ".venv", "__pycache__", "node_modules",
            ".hermes", "indexes",
            ".mypy_cache", ".pytest_cache", ".ruff_cache",
        }
        EXCLUDED_DIR_SUFFIXES = {".egg-info", ".eggs"}

        def _should_skip_dir(dirname: str) -> bool:
            if dirname in EXCLUDED_DIRS:
                return True
            if any(dirname.endswith(s) for s in EXCLUDED_DIR_SUFFIXES):
                return True
            if dirname.startswith(".") and dirname not in (".config", ".local", ".ssh"):
                return True
            return False

        def _walk_dirs(base_dir: Path):
            for root, dirs, files in os.walk(base_dir):
                dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
                yield root, dirs, files

        logger.info("🔍 Scan d'indexation démarré...")
        total = 0

        for base_dir in dirs_to_index:
            if not base_dir.exists():
                continue
            for root, _, files in _walk_dirs(base_dir):
                for file in files:
                    if any(file.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                        total += 1

        logger.info(f"📊 {total} fichiers éligibles trouvés au total")

        processed = 0
        indexed = 0
        for base_dir in dirs_to_index:
            if not base_dir.exists():
                continue
            for root, _, files in _walk_dirs(base_dir):
                for file in files:
                    if not any(file.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                        continue
                    filepath = os.path.join(root, file)

                    # Skip >500KB
                    try:
                        fsize = os.path.getsize(filepath)
                        if fsize > 500 * 1024:
                            logger.debug(
                                f"⏭️ Trop lourd ({fsize/1024:.0f} KB): {filepath}"
                            )
                            continue
                    except OSError:
                        continue

                    # RAM guard
                    import psutil
                    ram = psutil.virtual_memory()
                    if ram.available < 250 * 1024 * 1024:
                        logger.warning(
                            f"⚠️ RAM critique ({ram.available/1024**3:.1f} Go) — "
                            f"sauté: {filepath}"
                        )
                        continue
                    if ram.available < 500 * 1024 * 1024:
                        logger.warning(
                            f"⚠️ RAM insuffisante ({ram.available/1024**3:.1f} Go) — "
                            f"pause 30s avant {filepath}"
                        )
                        await asyncio.sleep(30)
                        ram = psutil.virtual_memory()
                        if ram.available < 500 * 1024 * 1024:
                            logger.warning(
                                f"⚠️ RAM toujours insuffisante après pause — "
                                f"sauté: {filepath}"
                            )
                            continue

                    await self.ingestion.index_file(filepath)
                    indexed += 1
                    processed += 1

                    if processed % 10 == 0 or processed == total:
                        logger.info(
                            f"📄 Indexation: {processed}/{total} traités ({indexed} indexés)"
                        )
                    await asyncio.sleep(0.5)

        logger.info(
            f"✅ Indexation terminée: {indexed}/{total} fichiers indexés."
        )
        return indexed

    async def _auto_index_with_ram_guard(self) -> None:
        """Auto-indexation périodique (conservée pour compatibilité)."""
        dirs_to_index = [
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
        ]
        await asyncio.sleep(60)
        while self._indexing_enabled:
            await self._run_index_cycle(dirs_to_index)
            # Attendre 1h avec arrêt possible
            for _ in range(360):
                if not self._indexing_enabled:
                    return
                await asyncio.sleep(10)

    # ── Phase 4 : Routes ModelRouter ──────────────────────────────────────────

    def _init_model_routes(self) -> None:
        """Configure les routes de modèles selon les providers réellement disponibles.

        AUDIT V16 FIX : routes dynamiques — ne charge que les providers qui ont
        une clé API dans le Keychain. Fin du hardcodage Groq qui n'est pas configuré.
        """
        from src.models.router import ModelRoute, TaskType
        routes: list[ModelRoute] = []

        # ── Routes cloud actuelle (provider configuré) ──
        cloud_prov = getattr(config, "cloud_provider", "opencode_zen")
        cloud_model = getattr(config, "cloud_model", "deepseek-v4-flash-free")
        routes.append(ModelRoute(
            name=f"{cloud_prov}/{cloud_model}",
            provider=cloud_prov,
            task_types=[TaskType.SIMPLE, TaskType.RAG, TaskType.TOOL, TaskType.COMPLEX],
            cost_per_1k_tokens=0.0,
            priority=10,
            avg_accuracy=0.90,
        ))

        # ── Provider fallback (cloud_fallback, ex: openrouter) ──
        fallback_str = getattr(config, "cloud_fallback", "")
        if fallback_str and "/" in fallback_str:
            fb_provider = fallback_str.split("/", 1)[0]
            _has_key = getattr(config, f"{fb_provider}_key", None) or \
                       getattr(config, f"{fb_provider.replace('-', '_')}_key", None)
            if _has_key:
                routes.append(ModelRoute(
                    name=fallback_str,
                    provider=fb_provider,
                    task_types=[TaskType.SIMPLE, TaskType.RAG, TaskType.COMPLEX, TaskType.CODE],
                    cost_per_1k_tokens=0.0001,
                    priority=5,
                    avg_accuracy=0.85,
                ))

        # ── Routes additionnelles : uniquement si le provider a une clé ──
        _extra_routes = [
            ("deepseek", "deepseek/deepseek-chat", [TaskType.COMPLEX, TaskType.CODE, TaskType.CREATIVE], 0.0005, 7, 0.90),
        ]
        for prov, name, task_types, cost, prio, acc in _extra_routes:
            _key = getattr(config, f"{prov}_key", None)
            if _key and prov != cloud_prov:  # éviter doublon si c'est déjà le provider actif
                routes.append(ModelRoute(
                    name=name, provider=prov,
                    task_types=task_types,
                    cost_per_1k_tokens=cost, priority=prio,
                    avg_accuracy=acc,
                ))

        # ── Local (toujours présent) ──
        local_model = getattr(config, "local_model", "phi-4-mini-4bit")
        local_name = f"local/{local_model.split('/')[-1]}"
        routes.append(ModelRoute(
            name=local_name, provider="local",
            task_types=list(TaskType),
            cost_per_1k_tokens=0.0, priority=1,
            avg_accuracy=0.80,
        ))

        for route in routes:
            self.model_router.add_route(route)
        logger.info(f"🗺️ ModelRouter: {len(routes)} routes configurées "
                     f"(provider: {cloud_prov})")

    def refresh_model_routes(self) -> None:
        """Rebuilt les routes du modèle après un changement de clé API ou de configuration.

        V17 FIX : appelé automatiquement via EventBus~api_keys_updated,
        ou manuellement pour recharger les routes sans restart.
        """
        self.model_router.clear_routes()
        self._init_model_routes()
        logger.info("🗺️ Routes ModelRouter reconstruites (sans restart)")

    # ── Phase 4 : MCP Tools ───────────────────────────────────────────────────

    def _register_mcp_tools(self) -> None:
        """Enregistre les outils NURU comme outils MCP."""
        from src.mcp.server import MCPTool

        # Tool: Recherche mémoire
        def _search_memory(**params):
            query = params.get("query", "")
            limit = params.get("limit", 5)
            try:
                results = self.memory.search(query, limit=limit)
                return {"results": results, "count": len(results)}
            except Exception as e:
                return {"error": str(e)}

        self.mcp_server.register_tool(MCPTool(
            name="search_memory",
            description="Recherche dans la mémoire persistante de NURU",
            parameters={"query": {"type": "string", "required": True}, "limit": {"type": "integer"}},
            handler=_search_memory,
        ))

        # Tool: Query RAG
        def _rag_query(**params):
            query = params.get("query", "")
            try:
                results = self.rag.search(query)
                if hasattr(results, 'to_dict'):
                    return results.to_dict()
                return str(results)
            except Exception as e:
                return {"error": str(e)}

        self.mcp_server.register_tool(MCPTool(
            name="rag_query",
            description="Interroge le moteur RAG documentaire",
            parameters={"query": {"type": "string", "required": True}},
            handler=_rag_query,
        ))

        # Tool: Knowledge Graph
        def _kg_query(**params):
            query = params.get("query", "")
            limit = params.get("limit", 10)
            try:
                nodes = self.knowledge_graph.search_nodes(query, limit=limit)
                return {"nodes": [n.to_dict() for n in nodes], "count": len(nodes)}
            except Exception as e:
                return {"error": str(e)}

        self.mcp_server.register_tool(MCPTool(
            name="knowledge_graph_search",
            description="Recherche dans le graphe de connaissances",
            parameters={"query": {"type": "string", "required": True}, "limit": {"type": "integer"}},
            handler=_kg_query,
        ))

        # Tool: Cost summary
        def _cost_summary(**params):
            try:
                return self.cost_guard.get_summary()
            except Exception as e:
                return {"error": str(e)}

        self.mcp_server.register_tool(MCPTool(
            name="cost_summary",
            description="Résumé des coûts API",
            parameters={},
            handler=_cost_summary,
        ))

        logger.info(f"🔌 MCP: {len(self.mcp_server.tools)} outils enregistrés")

    # ── Phase 3 : Proactive Engine ────────────────────────────────────────────

    def _register_proactive_collectors(self) -> None:
        """Enregistre les collecteurs de signaux pour le ProactiveEngine."""

        def _clock_collector():
            from src.proactive.engine import Signal, SignalCategory, SignalPriority
            import datetime
            now = datetime.datetime.now()
            signals = []
            # Rappel si proche d'un horaire de routine
            for routine in self.routines.get_active():
                due = self.routines.check_due(time.time())
                for r in due:
                    signals.append(Signal(
                        source="clock",
                        category=SignalCategory.REMINDER,
                        priority=SignalPriority.ROUTINE,
                        title=f"Routine due : {r.name}",
                        description=r.description,
                    ))
            return signals

        self.proactive.register_collector("clock", _clock_collector)

        def _memory_collector():
            """Collecteur basé sur les faits mémoire récents."""
            from src.proactive.engine import Signal, SignalCategory, SignalPriority
            signals = []
            try:
                facts = self.memory.get_recent_facts(limit=5)
                for fact in facts:
                    signals.append(Signal(
                        source="memory",
                        category=SignalCategory.INFO,
                        priority=SignalPriority.LOW,
                        title="Fait mémoire",
                        description=str(fact),
                    ))
            except Exception:
                pass
            return signals

        self.proactive.register_collector("memory", _memory_collector)

    # ── Phase 3 : Boucles background ──────────────────────────────────────────

    async def _sleep_cycle_loop(self) -> None:
        """Boucle périodique de mise à jour du cycle de sommeil."""
        from src.memory.sleep_cycle import SleepPhase
        while self._indexing_enabled:
            try:
                phase = self.sleep_cycle.tick()
                if phase == SleepPhase.DEEP and hasattr(self, '_on_deep_sleep'):
                    await self.event_bus.emit("sleep_phase", {"phase": phase.value})
                elif phase == SleepPhase.AWAKE:
                    await self.event_bus.emit("sleep_phase", {"phase": phase.value})
            except Exception as e:
                logger.debug(f"Sleep cycle tick: {e}")
            await asyncio.sleep(10)

    async def _proactive_collect_loop(self) -> None:
        """Boucle de collecte et évaluation proactives."""
        await asyncio.sleep(30)  # Laisser le temps à l'app de démarrer
        while self._indexing_enabled:
            try:
                signals = await self.proactive.collect_signals()
                if signals:
                    logger.info(f"⚡ Signaux proactifs: {len(signals)} collectés")
                    plan = await self.proactive.evaluate()
                    pending = plan.pending_actions()
                    for action in pending:
                        await self.event_bus.emit("proactive_action", action.to_dict())
            except Exception as e:
                logger.debug(f"Proactive collect: {e}")
            await asyncio.sleep(120)  # Collecte toutes les 2 minutes

    def build_system_prompt(self, intent: str, facts: list[str] = None,
                            procedures: str = "",
                            confidence_label: str | None = None) -> str:  # V16 FIX
        from src.identity_manager import IdentityManager
        identity = IdentityManager.load()
        static_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_name=identity["user_name"],
            user_full_name=identity["user_full_name"],
            user_profession=identity["user_profession"],
            user_specialty=identity["user_specialty"],
            user_organizations=identity["user_organizations"]
        )
        parts = [static_prompt]
        
        # Règles de réponse spécifiques à l'intention (surcouche au prompt de base)
        if intent == "RAG":
            parts.append("""
# RAPPEL RAG
Le CONTEXTE ci-dessous (entre === DÉBUT DU CONTEXTE === et === FIN DU CONTEXTE ===)
est la source principale. Applique les règles du MODE RAG STRICT ci-dessus.""".strip())
            # V16 FIX : Propager le niveau de confiance RAG au LLM
            if confidence_label:
                if confidence_label == "ABSENT":
                    parts.append("""
⚠️ CONFIANCE DOCUMENT : AUCUN DOCUMENT PERTINENT TROUVÉ
Aucun document correspondant n'a été trouvé dans la base RAG pour cette requête.
Ne tente PAS d'inventer des informations à partir de documents inexistants.
Réponds honnêtement que tu ne trouves pas d'information pertinente dans les sources,
et propose d'aider l'utilisateur à reformuler sa recherche.""".strip())
                elif confidence_label == "FAIBLE":
                    parts.append("""
⚠️ CONFIANCE DOCUMENT : FAIBLE
Les documents trouvés ont une faible pertinence par rapport à la requête.
Vérifie attentivement chaque information avant de l'utiliser.
Si les documents ne répondent pas correctement à la question, indique les limites.""".strip())
                elif confidence_label == "MOYENNE":
                    parts.append("""
ℹ️ CONFIANCE DOCUMENT : MOYENNE
Les documents trouvés sont modérément pertinents. Peux servir de base de réponse
mais vérifie les affirmations importantes contre le contexte.""".strip())
        elif intent == "COMPLEX":
            parts.append("""
# MODE RECHERCHE WEB
Le contexte ci-dessous contient des résultats de recherche Web. Applique le MODE HYBRIDE :
utilise les résultats Web en priorité, complète avec tes connaissances si nécessaire.""".strip())
        elif intent == "GENERAL":
            # V10.1 : Connaissances générales — réponse libre, pas de RAG
            parts.append("""
# MODE CONNAISSANCES GÉNÉRALES
Tu réponds avec tes connaissances internes. Pas de documents à référencer.
Si tu n'es pas certain de la réponse, indique-le honnêtement.""".strip())
        else: # SIMPLE (greetings, chit-chat)
            parts.append("""
# MODE CONVERSATION
Réponds de manière naturelle et chaleureuse. Les règles sur les sources et le RAG
ne s'appliquent pas pour les salutations et conversations simples.""".strip())
        
        if procedures.strip():
            parts.append(f"\n## Règles de comportement personnalisées\n{procedures.strip()}")
            
        if facts:
            facts_str = "\n".join(facts)
            if facts_str.strip():
                parts.append(f"\n## Ce que tu sais sur {identity['user_name']}\n{facts_str.strip()}")

        # V12.1 — ANTI-HALLUCINATION : informations personnelles
        parts.append(f"""
# RÈGLE STRICTE : INFORMATIONS PERSONNELLES SUR L'UTILISATEUR
Quand on te parle de {identity["user_name"]} (son identité, âge, vie, travail, projets, nationalité, résidence) :
- Utilise UNIQUEMENT les faits listés dans ## Ce que tu sais sur {identity["user_name"]} ci-dessus.
- N'INVENTE JAMAIS d'informations personnelles qui n'y figurent pas.
- Si les faits sont insuffisants pour répondre, dis-le honnêtement : "Je ne dispose pas
  de cette information dans ma mémoire à propos de {identity["user_name"]}."
- Ne comble PAS les lacunes avec des suppositions, généralités ou stéréotypes.
- Exemple à ne PAS suivre : "Sa couleur préférée est le bleu" → si ce fait n'est pas
  dans ## Ce que tu sais sur {identity["user_name"]}, ne l'invente pas.
""".strip())

        # ── Phase 3 : Contexte augmenté ──
        try:
            kg_nodes = self.knowledge_graph.search_nodes("", limit=5)
            if kg_nodes:
                kg_block = "\n".join(f"- {n.label} ({n.entity_type})" for n in kg_nodes)
                parts.append(f"\n## Connaissances reliées (Knowledge Graph)\n{kg_block}")
        except Exception:
            pass

        try:
            phase = self.sleep_cycle.current_phase
            if phase.value != "awake":
                from src.memory.sleep_cycle import SleepPhase
                phase_names = {SleepPhase.AWAKE.value: "éveillé", SleepPhase.LIGHT.value: "sommeil léger",
                              SleepPhase.DEEP.value: "sommeil profond", SleepPhase.REM.value: "sommeil paradoxal"}
                parts.append(f"\n## Statut NURU\nÉtat : {phase_names.get(phase.value, phase.value)}")
        except Exception:
            pass
        return "\n".join(parts)


    async def process_query(self, query: str, use_tts: bool = False, stream_session=None) -> AsyncGenerator[str, None]:
        """Traite une requête utilisateur en déléguant au NuruOrchestrator.

        Délègue l'intégralité du pipeline (routage, RAG, génération,
        vérification, mémoire) au NuruOrchestrator injecté.
        """
        # ── Phase 3 : Signal d'activité utilisateur ──
        self.sleep_cycle.user_activity_detected()

        async for token in self.orchestrator.process_query(
            query=query, session_id="default",
            use_tts=use_tts, audio_engine=self.audio if use_tts else None,
            stream_session=stream_session,
        ):
            yield token

        # Extraction post-session déportée en background.
        # V10.3k : utilise le bookkeeping _bg_tasks pour éviter
        # "Task was destroyed but it is pending!" à la fermeture de loop.
        await self._schedule_background_extraction()

    async def _schedule_background_extraction(self) -> None:
        """Planifie l'extraction post-session en arrière-plan.

        Crée une task asyncio, la garde en référence via self._bg_tasks
        pour éviter la destruction par le GC quand l'event loop se ferme,
        et l'enlève automatiquement du set quand elle se termine.

        Voir AUDIT B-Task-Destroyed (Top 20 #9).
        """
        async def background_extraction():
            try:
                history = self.memory.get_recent_history(limit=20)
                facts = await asyncio.to_thread(self._extractor.extract, history)
                for fact in facts:
                    self.memory.add_fact(fact, category="user_profile")
            except Exception as e:
                logger.debug(f"Extraction post-session: {e}")

        task = asyncio.create_task(background_extraction())
        self._bg_tasks.add(task)
        # Auto-cleanup quand la task finit (évite accumulation)
        task.add_done_callback(self._bg_tasks.discard)

    def warmup(self):
        """Initialisation préventive des modèles."""
        self.local_llm.warmup()

