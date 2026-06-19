import asyncio
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator
from src.config import config
from src.rag_engine import RAGEngine, RAGResult
from src.semantic_router import SemanticRouter  # V4 : Remplace IntentClassifier
from src.core.router import Router  # V5 : Routeur avec PolicyEngine et route_with_context
from src.llm_local import LocalLLM
from src.llm_cloud import CloudLLM
from src.memory_store import MemoryStore
from src.audio import AudioEngine
from src.cloud import WebSearch
from src.context_manager import ContextBudget
from src.runtime_manager import RuntimeManager
from src.core.events import EventBus
# NURU V10.3 — AUDIT-FIX : PluginSystem et ReflectionEngine supprimés (Arch-01).
# Étaient des stubs legacy (YAGNI) qui ajoutaient du bruit dans NuruCore.__init__
# et correspondaient à du code mort — aucun call site ne les utilisait réellement.
# Si un vrai système de plugins est nécessaire un jour, il sera ajouté frais
# dans un module dédié (src/plugins/) avec tests et DI explicite.
from src.ingestion import IngestionEngine, SUPPORTED_EXTENSIONS
from src.ram_monitor import RAMMonitor  # V4 : Monitoring RAM
from src.document_watcher import DocumentWatcher  # V4.5 : Auto-indexation watchdog
from src.core.orchestrator import NuruOrchestrator  # V4.5 : Nouvel orchestrateur
from src.core.policies import PolicyEngine  # V4.5 : Moteur de politiques
from src.extraction import PostSessionExtractor  # V4.5 : Extraction post-session
from src.long_term_memory import LongTermMemory  # V10.1 : Mémoire long terme
from src.memory_bridge import MemoryBridge  # V10.1 : Pont V5+V9

logger = logging.getLogger(__name__)


# ── Guard anti-conflit V8+ ──
# NuruCore (ce module) ET NuruOrchestrator (importé ligne 29) cohabitent
# pendant la migration V4.5→V8+. Ce guard avertit que les deux pipelines
# sont chargés simultanément, ce qui consomme de la RAM inutilement.
# À supprimer quand NuruCore sera entièrement migré vers l'orchestrateur.
if "NuruOrchestrator" in dir():
    logger.warning(
        "⚠️ NuruCore ET NuruOrchestrator chargés — migration V4.5→V8+ en cours. "
        "Les nouveaux pipelines doivent utiliser NuruOrchestrator directement."
    )

SYSTEM_PROMPT_STATIC = """
Tu es NURU V8+, l'assistant IA personnel de Leblanc.

Ton utilisateur : Leblanc BAHIGA Mudarhi — Ingénieur agronome & informaticien, spécialiste des chaînes de valeur agricoles en Afrique centrale et orientale (IITA, FAO, World Bank, USAID).

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
    """Orchestrateur asynchrone principal de NURU V4."""
    
    def __init__(self):
        # V4 : Routeur Sémantique Hybride (remplace le simple IntentClassifier)
        self.rag = RAGEngine()
        self.cloud_llm = CloudLLM()  # V10.1 : déplacé AVANT le router pour classification
        self.router = Router(rag_engine=self.rag, is_online_check=self._is_online,
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
        self.ingestion = IngestionEngine()
        
        # V4 : Monitoring RAM actif
        # V10.3k — audit Option C : seuils lus depuis Config (surchargeables via YAML/env)
        self.ram_monitor = RAMMonitor(
            warning_threshold_gb=getattr(config, "ram_warning_threshold_gb", 1.0),
            critical_threshold_gb=getattr(config, "ram_critical_threshold_gb", 0.5),
        )
        # Connecte le déchargement du reranker au RAMMonitor
        self.ram_monitor.register_callback(self.rag.clear_reranker)
        self.ram_monitor.start()

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
            # V10.3 — AUDIT Arch-01 : reflection_engine=None (ref stubs supprimés)
            reflection_engine=None,
            system_prompt_builder=self.build_system_prompt,  # V4.5 : callback prompt
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

    def _is_online(self) -> bool:
        """Vérifie rapidement si le fournisseur Cloud est accessible.
        
        V8+ : Multi-provider — teste Groq, puis OpenRouter, puis DeepSeek.
        Timeout 0.5s par tentative. Retourne True dès qu'un provider répond.
        """
        import socket
        hosts = [
            ("api.groq.com", 443),
            ("openrouter.ai", 443),
            ("api.deepseek.com", 443),
        ]
        for host, port in hosts:
            try:
                socket.create_connection((host, port), timeout=0.5)
                return True
            except (socket.timeout, OSError):
                continue
        return False

    async def _check_cloud_online(self) -> bool:
        """Version asynchrone de _is_online pour utilisation dans process_query.
        
        Teste TOUS les hosts en parallèle avec timeout global de 0.8s.
        V8+ : Vérifie la connectivité AVANT d'engager le pipeline RAG.
        """
        import socket
        hosts = [
            "api.groq.com",
            "openrouter.ai",
            "api.deepseek.com",
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
        return any(results)
        
    def start_background_tasks(self):
        """Lance les tâches asynchrones et le watcher en arrière-plan.
        
        V11.2 : Auto-indexation réactivée avec RAM guard
        Le watcher temps réel continue de fonctionner normalement.
        """
        # V11.2 : Auto-indexation réactivée avec RAM guard
        # Vérifie la RAM avant chaque fichier pour éviter la saturation
        asyncio.create_task(self._auto_index_with_ram_guard())
        # V4.5 : Document watcher (watchdog) pour auto-indexation temps réel
        self._watcher = DocumentWatcher(index_callback=self.ingestion.index_file)
        self._watcher.start()
        logger.info("📁 Document watcher démarré (surveille Documents, Desktop, Downloads)")

    async def _auto_index_with_ram_guard(self) -> None:
        """Auto-indexation périodique avec protection RAM (V11.2).

        Scanne ~/Documents, ~/Desktop, ~/Downloads toutes les 3600s.
        Vérifie RAM libre > 500 MB avant chaque fichier pour
        éviter la saturation sur M1 8 Go.
        Le watcher temps réel continue de gérer les modifications.
        """
        dirs_to_index = [
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
        ]

        # 1. Attendre 60s au démarrage (laisser le temps à l'app de charger)
        await asyncio.sleep(60)

        while True:
            logger.info("🔍 Scan auto-indexation V11.2 (RAM guard) démarré...")
            total = 0
            indexed = 0

            # Compter d'abord le total de fichiers éligibles
            for base_dir in dirs_to_index:
                if not base_dir.exists():
                    continue
                for root, _, files in os.walk(base_dir):
                    for file in files:
                        if any(file.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                            total += 1

            logger.info(f"📊 {total} fichiers éligibles trouvés au total")

            processed = 0
            for base_dir in dirs_to_index:
                if not base_dir.exists():
                    continue
                for root, _, files in os.walk(base_dir):
                    for file in files:
                        if not any(file.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
                            continue
                        filepath = os.path.join(root, file)

                        # 3. Vérifier RAM libre > 500 MB
                        import psutil
                        ram = psutil.virtual_memory()
                        if ram.available < 500 * 1024 * 1024:  # 500 MB
                            logger.warning(
                                f"⚠️ RAM insuffisante ({ram.available / 1024**3:.1f} Go dispo) — "
                                f"pause 60s avant {filepath}"
                            )
                            await asyncio.sleep(60)
                            # Réessayer la vérification après la pause
                            ram = psutil.virtual_memory()
                            if ram.available < 500 * 1024 * 1024:
                                logger.warning(
                                    f"⚠️ RAM toujours insuffisante après pause — "
                                    f"fichier sauté: {filepath}"
                                )
                                continue

                        # 5. Indexer le fichier
                        await self.ingestion.index_file(filepath)
                        indexed += 1

                        processed += 1
                        # 8. Log le progrès
                        if processed % 10 == 0 or processed == total:
                            logger.info(
                                f"📄 Auto-indexation: {processed}/{total} fichiers "
                                f"traités ({indexed} indexés)"
                            )

                        # 6. Pause entre chaque fichier
                        await asyncio.sleep(0.5)

            logger.info(
                f"✅ Cycle auto-indexation terminé: "
                f"{indexed}/{total} fichiers indexés. "
                f"Prochain scan dans 1h."
            )
            # 7. Attendre 3600s avant le prochain scan
            await asyncio.sleep(3600)

    def build_system_prompt(self, intent: str, facts: list[str] = None, procedures: str = "") -> str:
        """Assemble le prompt système de base avec les faits et procédures, adapté selon l'intention."""
        parts = [SYSTEM_PROMPT_STATIC]
        
        # Règles de réponse spécifiques à l'intention (surcouche au prompt de base)
        if intent == "RAG":
            parts.append("""
# RAPPEL RAG
Le CONTEXTE ci-dessous (entre === DÉBUT DU CONTEXTE === et === FIN DU CONTEXTE ===)
est la source principale. Applique les règles du MODE RAG STRICT ci-dessus.""".strip())
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
                parts.append(f"\n## Ce que tu sais sur Leblanc\n{facts_str.strip()}")
                
        return "\n".join(parts)

    def _detect_model_family(self, intent: str) -> str:
        """Détecte la famille du modèle local pour formater le prompt correctement."""
        if intent == "COMPLEX":
            return "phi"
        try:
            model_id = self.local_llm._get_required_model(intent)
            if "phi" in model_id.lower():
                return "phi"
            if "gemma" in model_id.lower():
                return "gemma"
        except Exception:
            pass
        return "phi"

    async def process_query(self, query: str, use_tts: bool = False) -> AsyncGenerator[str, None]:
        """Traite une requête utilisateur en déléguant au NuruOrchestrator.

        Délègue l'intégralité du pipeline (routage, RAG, génération,
        vérification, mémoire) au NuruOrchestrator injecté.
        """
        async for token in self.orchestrator.process_query(
            query=query, session_id="default",
            use_tts=use_tts, audio_engine=self.audio if use_tts else None,
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

    # ═══════════════════════════════════════════
    # V4.5 : Pipeline via NuruOrchestrator
    # ═══════════════════════════════════════════

    async def process_query_v45(self, query: str, use_tts: bool = False) -> AsyncGenerator[str, None]:
        """Version V4.5 du pipeline utilisant le NuruOrchestrator."""
        async for token in self.orchestrator.process_query(
            query=query, session_id="default",
            use_tts=use_tts, audio_engine=self.audio if use_tts else None,
        ):
            yield token

        # V10.3k — même correctif B-Task-Destroyed via _schedule_background_extraction
        await self._schedule_background_extraction()

