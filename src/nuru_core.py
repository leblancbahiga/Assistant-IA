import asyncio
import logging
import time
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
# NURU V5 : plugin_system supprimé
PluginSystem = object  # stub
# NURU V5 : reflection_engine supprimé
class ReflectionEngine:
    """Stub pour compatibilité ascendante."""
    async def analyze(self, *args, **kwargs):
        return {}
    def add_reflection(self, *args, **kwargs):
        pass
from src.ingestion import IngestionEngine
from src.ram_monitor import RAMMonitor  # V4 : Monitoring RAM
from src.document_watcher import DocumentWatcher  # V4.5 : Auto-indexation watchdog
from src.core.orchestrator import NuruOrchestrator  # V4.5 : Nouvel orchestrateur
from src.core.policies import PolicyEngine  # V4.5 : Moteur de politiques
from src.extraction import PostSessionExtractor  # V4.5 : Extraction post-session

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_STATIC = """
Tu es NURU V4.5, l'assistant IA personnel de Leblanc.

Ton utilisateur : Leblanc BAHIGA Mudarhi — Ingénieur agronome & informaticien, spécialiste des chaînes de valeur agricoles en Afrique centrale et orientale (IITA, FAO, World Bank, USAID).

Ta mission principale est de fournir des réponses exactes, traçables, utiles et adaptées au contexte disponible.

# PRIORITÉ DES SOURCES
Lorsque des documents sont fournis via le système RAG :
1. Les documents utilisateur sont prioritaires.
2. Les informations doivent être recherchées en priorité dans ces documents.
3. Si plusieurs documents sont disponibles, croise les informations avant de répondre.

# MODE RAG STRICT
Lorsque la question porte explicitement sur les documents fournis :
- Utilise uniquement les informations présentes dans les sources.
- N'invente jamais une information absente.
- Cite systématiquement la source utilisée.
- Si l'information n'existe pas dans les documents, réponds :
  "Je ne trouve pas cette information dans les documents fournis."

# MODE HYBRIDE
Lorsque les documents ne contiennent qu'une partie de la réponse :
- Commence par exploiter les documents.
- Complète uniquement avec des connaissances générales clairement identifiées comme telles.
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
        self.router = Router(rag_engine=self.rag, is_online_check=self._is_online)
        self.web = WebSearch()
        self.local_llm = LocalLLM()
        self.cloud_llm = CloudLLM()
        self.memory = MemoryStore()
        self.audio = AudioEngine()
        self.context_budget = ContextBudget(
            max_prompt_tokens=4096, # Augmenté pour V4
            reserved_response=1024
        )
        self.runtime = RuntimeManager()
        self.event_bus = EventBus()
        self.plugins = PluginSystem()
        self.reflection = ReflectionEngine()
        self.ingestion = IngestionEngine()
        
        # V4 : Monitoring RAM actif
        self.ram_monitor = RAMMonitor(
            warning_threshold_gb=2.0,
            critical_threshold_gb=1.0
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
            reflection_engine=self.reflection,
            system_prompt_builder=self.build_system_prompt,  # V4.5 : callback prompt
        )
        logger.info("🚀 NuruOrchestrator V4.5 initialisé")

        # V4.5 : Extracteur post-session (profil utilisateur)
        self._extractor = PostSessionExtractor()
        
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
        
        NURU V6 : auto_index_loop suspendue — l'index est construit 
        manuellement via reindex_personal.py pour éviter la saturation RAM.
        """
        # V6 : Auto-indexation suspendue (sature la RAM sur M1 8 Go)
        # asyncio.create_task(self.ingestion.auto_index_loop())
        # V4.5 : Document watcher (watchdog) pour auto-indexation temps réel
        self._watcher = DocumentWatcher(index_callback=self.ingestion.index_file)
        self._watcher.start()
        logger.info("📁 Document watcher démarré (surveille Documents, Desktop, Downloads)")

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
        else: # SIMPLE (greetings, chit-chat, small tasks)
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
        """Traite une requête utilisateur et génère une réponse en streaming (V4).

        ⚠️ Pipeline V4 legacy — préférer process_query_v45() pour le pipeline V4.5
        qui utilise NuruOrchestrator (src/core/orchestrator.py) avec injection
        de dépendances, policies, et EvidenceVerifier intégré.

        Les deux pipelines coexistent. process_query() est maintenu pour
        compatibilité avec le dashboard existant.
        """
        
        # 1. Routage Sémantique V4 (remplace le simple IntentClassifier)
        route_result = await self.router.route(query)
        intent = route_result.decision  # SIMPLE | LOCAL_RAG | CLOUD_GROQ | CLARIFICATION
        
        # Convertir les décisions du routeur en intentions pour le reste du pipeline
        if intent == "LOCAL_RAG":
            intent_internal = "RAG"
        elif intent == "CLOUD_GROQ":
            intent_internal = "COMPLEX"
        elif intent == "CLARIFICATION":
            intent_internal = "SIMPLE"
            clarification_hint = True
        else:
            intent_internal = "SIMPLE"
        
        logger.info(
            f"🧠 Routage: {query[:40]}... → {intent} "
            f"(confiance: {route_result.confidence:.2f}, "
            f"RAG score: {route_result.rag_top_score:.2f})"
        )
        
        # 2. Vérification du Cache Sémantique (sauf pour les requêtes complexes)
        if intent_internal != "COMPLEX":
            cached_resp = await self.memory.get_cache(query)
            if cached_resp:
                await self.event_bus.emit("cache_hit", {"query": query})
                if use_tts:
                    asyncio.create_task(self.audio.speak(cached_resp))
                yield cached_resp
                return
        
        # 2b. V8+ : Vérification Cloud en tête de pipeline RAG
        # Si le cloud est indisponible, on bascule sur Phi-4-mini
        # avec contexte tronqué avant d'engager la recherche.
        cloud_available = True
        if intent_internal in ["RAG", "COMPLEX"]:
            cloud_available = await self._check_cloud_online()
            if not cloud_available:
                logger.warning("☁️ Cloud indisponible — bascule en mode dégradé local")
                yield "⚠️ **Mode hors-ligne** : service cloud indisponible. Analyse documentaire limitée.\n\n"

        # 3. Récupération du Contexte (RAG et/ou WEB)
        context_tasks = []
        if intent_internal in ["RAG", "COMPLEX"]:
            context_tasks.append(self.rag.retrieve(query))
        
        if intent_internal == "COMPLEX":
            context_tasks.append(self.web.search(query))
        
        if context_tasks:
            contexts = await asyncio.gather(*context_tasks)
            rag_result = RAGResult()
            rag_context = ""
            web_context = ""
            for c in contexts:
                if isinstance(c, tuple):
                    rag_context, rag_result = c
                elif isinstance(c, str):
                    web_context = c
                else:
                    rag_context = str(c)
        else:
            rag_context = ""
            rag_result = RAGResult()
            web_context = ""
        
        # V8+ : Fallback offline — troncature agressive pour Phi-4-mini
        if not cloud_available and rag_context:
            # Garder seulement les 1000 premiers caractères (~250 tokens)
            rag_context = rag_context[:1000]
            if rag_context:
                rag_context = "[MODE DÉGRADÉ — Contexte fortement condensé]\n" + rag_context
            logger.warning(f"📉 Mode hors-ligne : contexte tronqué à {len(rag_context)} chars")

        # 3b. Fallback Web si RAG vide sur question informative
        if intent_internal == "RAG" and not rag_context and len(query.split()) > 3:
            logger.info("RAG insuffisant, tentative de fallback Web automatique...")
            yield " [⚠️ Aucun document pertinent trouvé. Bascule sur la recherche Web...] \n"
            web_context = await self.web.search(query)
            if web_context:
                intent_internal = "COMPLEX"
        
        # 4. Construction du Prompt via ContextBudget
        facts = self.memory.get_recent_facts(limit=20)
        history = self.memory.get_recent_history(limit=8)
        procedures = self.memory.get_procedures()
        
        # Message Système dynamique
        system_msg = self.build_system_prompt(intent=intent_internal, facts=facts, procedures=procedures)
        
        # Assemblage final du contexte documentaire
        if intent_internal == "COMPLEX":
            full_rag_context = web_context + ("\n\n" + rag_context if rag_context else "")
        else:
            full_rag_context = rag_context
        
        # ContextBudget
        model_family = self._detect_model_family(intent_internal)
        full_prompt = self.context_budget.allocate(
            system=system_msg,
            rag=full_rag_context,
            facts=facts,
            history=history,
            include_system=(intent_internal != "COMPLEX"),
            model_family=model_family
        )
        # Ajouter la requête utilisateur
        if intent_internal == "COMPLEX":
            full_prompt += f"\n## QUESTION À TRAITER :\n{query}"
        elif model_family == "phi":
            full_prompt += f"{query}<|end|>\n<|assistant|>\n"
        else:
            full_prompt += f"{query}\n<|assistant|>\n"

# ═══════════════════════════════════════════
        # 5. Sélection du Pipeline d'Inférence (Local par défaut, Cloud si besoin)
        # ═══════════════════════════════════════════
        response_content = ""
        sentence_buffer = ""
        start_gen_time = None  # Correction 9 : Chrono déclenché au premier token uniquement

        async def run_inference(source_gen):
            nonlocal response_content, sentence_buffer, start_gen_time
            background_tts_tasks = set()  # Correction 5 : Références fortes TTS
            async for token in source_gen:
                # Correction 9 : Le chrono démarre au premier vrai token
                if start_gen_time is None:
                    start_gen_time = time.time()
                    
                if token.startswith('<|') or token in ('</s>', '<s>'):
                    continue
                response_content += token
                sentence_buffer += token
                yield token

                if use_tts and any(c in token for c in ".!?\n"):
                    clean_sentence = sentence_buffer.strip()
                    if len(clean_sentence) > 5:
                        # Correction 5 : Strong reference + auto-nettoyage
                        task = asyncio.create_task(self.audio.speak(clean_sentence))
                        background_tts_tasks.add(task)
                        task.add_done_callback(background_tts_tasks.discard)
                        sentence_buffer = ""

        # ═══════════════════════════════════════════
        # V8+ : Sélection du Pipeline d'Inférence
        # Cloud par défaut pour tout travail documentaire
        # ═══════════════════════════════════════════
        # cloud_available est défini plus haut (Task 0.5)
        use_cloud = True
        
        if intent_internal == "SIMPLE" or not cloud_available:
            use_cloud = False
            if not cloud_available and intent_internal in ("RAG", "COMPLEX"):
                logger.warning("☁️ Cloud indisponible — bascule locale (contexte tronqué)")
        
        logger.info(
            f"{'☁️' if use_cloud else '💻'} Inférence "
            f"{'CLOUD' if use_cloud else 'LOCALE'} "
            f"({intent_internal}, cloud_ok={cloud_available})"
        )

        if use_cloud:
            await self.event_bus.emit("generation_started", {
                "model": config.cloud_model.split("/")[-1][:25],
                "model_id": config.cloud_model,
                "route": "CLOUD",
                "intent": intent,
                "temperature": 0.7,
            })
            async for token in run_inference(self.cloud_llm.generate_stream(
                prompt=full_prompt,
                intent=intent,
                system_prompt=system_msg
            )):
                yield token
        else:
            logger.info(
                f"💻 Inférence locale ({intent_internal}, "
                f"score={route_result.rag_top_score:.2f})"
            )
            local_model_id = self.local_llm._current_model_id or config.local_model
            await self.event_bus.emit("generation_started", {
                "model": local_model_id.split("/")[-1][:25],
                "model_id": local_model_id,
                "route": "LOCAL",
                "intent": intent,
                "temperature": getattr(self.local_llm, '_last_temperature', 0.7),
            })
            try:
                async for t in self.runtime.schedule_generator(
                    "generation",
                    run_inference(self.local_llm.generate_stream(full_prompt, intent=intent))
                ):
                    yield t
            except Exception as e:
                logger.error(f"Échec local : {e}. Bascule Cloud...")
                yield " [⚠️ Bascule Cloud...] "
                await self.event_bus.emit("generation_escalated", {"reason": str(e)})
                async for t in run_inference(self.cloud_llm.generate_stream(
                    prompt=full_prompt,
                    intent=intent,
                    system_prompt=system_msg
                )):
                    yield t

        # 6. V8+ Sprint 5 : Détection d'échec + Vérificateur + Reformulation
        _already_retried = False
        _already_fact_checked = False

        # 6a. Détection d'échec sur métriques objectives (5.1)
        if response_content and intent_internal in ('RAG', 'COMPLEX'):
            rag_conf = rag_result.confidence_label if hasattr(rag_result, 'confidence_label') else 'HAUTE'
            rag_chunks = rag_result.chunks_injected if hasattr(rag_result, 'chunks_injected') else 0
            rag_max_score = rag_result.top_score if hasattr(rag_result, 'top_score') else 0.0

            needs_retry = (
                rag_conf in ('FAIBLE', 'ABSENT')
                and rag_chunks == 0
                and rag_max_score < 0.30
                and not _already_retried
            )

            # 6b. Reformulation Cloud 2ème passe (5.4)
            if needs_retry and use_cloud:
                _already_retried = True
                logger.info(
                    f"🔄 Sprint 5 : Échec détecté (conf={rag_conf}, chunks={rag_chunks}, "
                    f"score={rag_max_score:.2f}) — Reformulation 2ème passe"
                )
                yield "\n\n🔄 **Recherche élargie...**\n"

                # Reformuler la requête avec CloudLLM
                reformulation_prompt = (
                    "Réécris cette question en utilisant des termes plus précis "
                    "et spécifiques pour améliorer la recherche documentaire :\n"
                    f"Question : {query}\n\n"
                    "Réponse (uniquement la reformulation, sans explication) :"
                )
                try:
                    reformulated = self.cloud_llm.generate(reformulation_prompt, timeout=5.0)
                    if reformulated and reformulated.strip():
                        reformulated = reformulated.strip()
                        logger.info(f"🔄 Reformulation : '{query[:40]}' -> '{reformulated[:60]}'")

                        # Nouvelle recherche RAG avec la requête reformulée
                        new_context, new_result = await self.rag.retrieve(reformulated)

                        if new_context:
                            # Nouveau prompt avec le nouveau contexte
                            new_full_rag = f"[CONFIANCE RAG: {new_result.confidence_label}]\n{new_context}"
                            new_full_prompt = self.context_budget.allocate(
                                system=system_msg,
                                rag=new_full_rag,
                                facts=facts,
                                history=history,
                                include_system=(intent_internal != "COMPLEX"),
                                model_family=model_family
                            )
                            if intent_internal == "COMPLEX":
                                new_full_prompt += f"\\n## QUESTION À TRAITER :\\n{query}"
                            elif model_family == "phi":
                                new_full_prompt += f"{query}<|end|>\\n<|assistant|>\\n"
                            else:
                                new_full_prompt += f"{query}\\n<|assistant|>\\n"

                            # Nouvelle génération Cloud
                            new_response = ""
                            async for token in run_inference(self.cloud_llm.generate_stream(
                                prompt=new_full_prompt,
                                intent=intent,
                                system_prompt=system_msg
                            )):
                                yield token
                                new_response += token

                            if new_response:
                                response_content = new_response
                                # Mettre à jour les métriques
                                rag_result = new_result
                                logger.info(f"🔄 2ème passe terminée ({len(new_response)} chars)")
                except Exception as e:
                    logger.warning(f"Reformulation échouée: {e}")

            # 6c. Vérificateur de faits Cloud (5.3) — seulement si pas déjà retryé
            if (not needs_retry or _already_retried) and not _already_fact_checked and use_cloud and response_content:
                try:
                    from src.rag.fact_checker import FactChecker
                    checker = FactChecker(cloud_llm=self.cloud_llm)

                    sources_text = [s.get('preview', '') for s in rag_result.sources if hasattr(rag_result, 'sources')]
                    if not sources_text:
                        sources_text = [rag_context[:500]] if rag_context else []

                    if sources_text and len(response_content) > 50:
                        _already_fact_checked = True
                        check_result = await checker.verify(response_content, sources_text)

                        if not check_result.verified and check_result.issues:
                            logger.info(f"🔍 Vérificateur : {len(check_result.issues)} problème(s)")

                            # 6d. Message UI si échec vérification (5.6)
                            yield "\n\n---\n⚠️ **Avertissement** : Certaines informations n'ont pu être vérifiées contre les sources disponibles."
                            for issue in check_result.issues[:2]:
                                yield f"\n- {issue[:120]}"
                except Exception as e:
                    logger.debug(f"FactChecker ignoré: {e}")

        # 7. Post-Processing & Mémoire (suite)
        if response_content:
            duration = time.time() - start_gen_time
            tokens_count = len(response_content) // 4
            tokens_prompt = self.context_budget._estimate_tokens(full_prompt) if hasattr(self.context_budget, '_estimate_tokens') else len(full_prompt) // 4
            
            # Déterminer les métriques du cockpit
            active_model_id = self.local_llm._current_model_id or config.local_model if intent != "COMPLEX" else config.cloud_model
            active_model = active_model_id.split("/")[-1][:25]
            active_route = "LOCAL" if intent != "COMPLEX" else "CLOUD"
            rag_score = self.rag.last_top_score
            tps = tokens_count / duration if duration > 0 else 0
            temperature = 0.7
            
            # Température réelle depuis le LLM local
            if hasattr(self.local_llm, '_last_temperature'):
                temperature = self.local_llm._last_temperature
            
            self.runtime.update_generation_stats(
                tokens=tokens_count,
                seconds=duration,
                model=active_model,
                route=active_route,
                rag_score=rag_score,
                temperature=temperature,
                tokens_prompt=tokens_prompt,
                context_max=self.context_budget.max_prompt_tokens,
                model_path=active_model_id
            )
            
            if use_tts and sentence_buffer.strip():
                # On utilise le scheduler pour le TTS aussi
                await self.runtime.schedule_task(
                    "tts", 
                    self.audio.speak(sentence_buffer.strip())
                )
                
            if intent != "COMPLEX":
                diag = getattr(rag_result, 'diagnostic', None)
                await self.memory.set_cache(query, response_content, diagnostic=diag)
            self.memory.add_message("user", query)
            self.memory.add_message("assistant", response_content)
            event_data = {
                "tokens": tokens_count,
                "tokens_prompt": tokens_prompt,
                "context_used": tokens_prompt,
                "context_max": self.context_budget.max_prompt_tokens,
                "seconds": round(duration, 2),
                "tps": round(tps, 2),
                "model": active_model,
                "model_id": active_model_id,
                "route": active_route,
                "rag_score": round(rag_score, 2),
                "temperature": temperature,
                "intent": intent,
                "rag_result": {
                    "documents_found": rag_result.documents_found,
                    "chunks_retrieved": rag_result.chunks_retrieved,
                    "chunks_injected": rag_result.chunks_injected,
                    "top_score": rag_result.top_score,
                    "retrieval_time_ms": rag_result.retrieval_time_ms,
                    "sources": rag_result.sources,
                    "rejected_chunks": rag_result.rejected_chunks,
                    "rejection_reason": rag_result.rejection_reason,
                    "query_rewritten": rag_result.query_rewritten,
                    "tokens_injected": rag_result.tokens_injected,
                },
            }
            await self.event_bus.emit("generation_complete", event_data)
            
            # 7. Réflexion & Auto-amélioration
            analysis = self.reflection.analyze(
                query=query, 
                response=response_content,
                metadata={
                    "intent": intent, 
                    "latency_ms": int(duration * 1000),
                    "tokens_per_sec": tokens_count / duration if duration > 0 else 0
                }
            )
            self.memory.add_reflection(
                query=query,
                feedback=f"Risk: {analysis['hallucination_risk']}, Concision: {analysis['concision_score']}",
                score=1.0 - analysis['hallucination_risk']
            )
            await self.event_bus.emit("reflection_complete", analysis)

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

        # Correction 8 : Extraction post-session déportée en background (évite freeze UI)
        async def background_extraction():
            try:
                history = self.memory.get_recent_history(limit=20)
                facts = await asyncio.to_thread(self._extractor.extract, history)
                for fact in facts:
                    self.memory.add_fact(fact, category="user_profile")
            except Exception as e:
                logger.debug(f"Extraction post-session: {e}")
        asyncio.create_task(background_extraction())
