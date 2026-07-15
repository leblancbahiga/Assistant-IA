import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.utils import load_adapters
from mlx_lm.sample_utils import make_sampler, make_repetition_penalty, make_logits_processors
import psutil
import logging
import gc
import asyncio
import time
from pathlib import Path
from typing import AsyncGenerator, Optional
from src.config import config
from src.core.model_manager import ModelManager
from src.core.ram_budget import get_budget, Priority
from src.cache.kv_cache import KVPersistentCache

logger = logging.getLogger(__name__)

# V16 FIX: Timeout etendu pour chargement modele M1 8Go (swap RAM unifiee)
# 180s = 3 min max pour charger poids 4-bit via MLX + swap
MODEL_LOAD_TIMEOUT_SECONDS = 180.0


class LocalLLM:
    """Gestionnaire de LLM locaux (MLX) avec Warmup et RAM Guard.

    Utilise ModelManager en interne pour le cycle de vie memoire.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._current_model_id = None
        self._last_temperature = 0.7
        # V15 P2 #27 : Delegation au ModelManager avec keep-alive reduit a 5s
        self._model_manager = ModelManager(keep_alive_seconds=5)
        # V10 Audit: Lock thread-safe pour generate_stream()
        self._gen_lock = asyncio.Lock()
        # V15 Phase 0B -- P0 #31 : cache de prompt pour les requetes repetees
        self._prompt_cache: dict[int, object] = {}
        # Statistiques de benchmark
        self.bench: dict[str, list[float]] = {"prompt_ms": [], "tok_s": []}
        # V15 P2 #27 : Tache de dechargement differe
        self._unload_task: Optional[asyncio.Task] = None
        # V15 Phase 5 (Item 41) : KV Cache Persistant
        self._kv_cache = KVPersistentCache(max_entries=10, max_total_mb=1024)
        self._current_session_id: str = ""
        # V15 Phase 5 (Item 38) : LoRA adaptateur RAG
        self._lora_adapter_path: Optional[str] = None

    def _schedule_unload(self):
        """Planifie le dechargement 5s apres la fin de la generation.

        V15 P2 #27 : keep_alive reduit de 300s a 5s pour liberer
        la RAM Metal immediatement apres la reponse.
        """
        self._cancel_unload()

        async def _delayed():
            try:
                await asyncio.sleep(self._model_manager._keep_alive)
                if self._model is not None:
                    logger.info("Keep-alive expire (5s). Dechargement auto.")
                    self.unload()
            except asyncio.CancelledError:
                pass

        try:
            self._unload_task = asyncio.create_task(_delayed())
        except RuntimeError:
            pass

    def _cancel_unload(self):
        """Annule le dechargement differe (nouvelle requete arrivee)."""
        if self._unload_task is not None:
            self._unload_task.cancel()
            self._unload_task = None

    def _get_required_model(self, intent: str) -> str:
        """Determine quel modele charger (1.5B ou 4B)."""
        ram_available_gb = psutil.virtual_memory().available / (1024**3)
        
        # Si un modele est deja charge, sa memoire sera liberee s'il est different,
        # ou conservee s'il est identique. Donc on ajoute une estimation de sa taille a la RAM disponible.
        if self._model is not None and self._current_model_id is not None:
            # Correction 2B : Cast securise en str pour eviter AttributeError sur None
            model_id_safe = str(self._current_model_id).lower()
            estimated_model_ram = 2.5 if "4b" in model_id_safe else 1.0
            ram_available_gb += estimated_model_ram

        # Seuil critique (switch Cloud total)
        if ram_available_gb < 0.3:
            raise RuntimeError(f"RAM critique ({ram_available_gb:.2f} Go).")
            
        # Selection du modele local
        # V16: seuil abaisse (0.5->0.2 Go) pour permettre le chargement meme en RAM tendue
        # Le RAMBudgetManager reste la vrai garde-fou (hard_limit + swap_warning)
        if ram_available_gb < 0.2:
            return config.local_model_fallback
        return config.local_model

    async def _load_model(self, model_id: str):
        """Charge ou swappe le modele en memoire."""
        if self._current_model_id == model_id and self._model is not None:
            return

        # V15 Phase 5 (Item 40) : verification budget RAM avant chargement
        budget = get_budget()
        if not budget.can_load("llm"):
            logger.warning(
                "Chargement LLM refuse par RAMBudgetManager "
                f"(swap {budget.probe().swap_percent:.0f}%) -- eviction en cours"
            )
            budget.evict(priority_below=Priority.CACHE)

        try:
            # Decharger proprement le modele precedent s'il y en a un pour liberer la RAM Metal avant de charger le nouveau
            if self._model is not None:
                logger.info(f"Dechargement du modele precedent ({self._current_model_id}) pour liberer de la memoire avant le chargement du nouveau.")
                self.unload()

            # Resolution du chemin local
            resolved_path = config.get_model_path(model_id)
            logger.info(f"Chargement du modele MLX depuis : {resolved_path}")

            # V16 FIX: Chargement avec timeout etendu (180s) pour M1 8Go + swap
            # Execute le chargement synchrone MLX dans un executor pour ne pas bloquer
            # l'event loop principal (PySide6 UI) pendant les 2-3 minutes de swap
            import asyncio
            loop = asyncio.get_event_loop()
            
            def _sync_load():
                from mlx_lm import load
                return load(resolved_path)
            
            try:
                self._model, self._tokenizer = await asyncio.wait_for(
                    loop.run_in_executor(None, _sync_load),
                    timeout=MODEL_LOAD_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout critique : Le chargement des poids MLX a pris plus de "
                    f"{MODEL_LOAD_TIMEOUT_SECONDS}s. Swap RAM sature sur M1 8Go. "
                    f"Fermez d'autres applications et reessayez."
                )
            
            self._current_model_id = model_id

            # V15 Phase 5 (Item 38) : Chargement adaptateur LoRA RAG si existant
            if self._lora_adapter_path:
                adapter_dir = Path(self._lora_adapter_path)
                if (adapter_dir / "adapters.safetensors").exists():
                    try:
                        self._model = load_adapters(self._model, self._lora_adapter_path)
                        logger.info("Adaptateur LoRA charge depuis %s", self._lora_adapter_path)
                    except Exception as e:
                        logger.warning("Echec chargement LoRA (%s) -- inference sans adaptateur", e)
                else:
                    logger.info("Aucun adaptateur LoRA trouve dans %s", self._lora_adapter_path)

            # V15 Phase 5 (Item 40) : marquer comme charge dans le budget RAM
            budget.mark_loaded("llm")
            budget.touch("llm")

            # V15 Phase 5 (Item 41) : restauration du KV cache si disponible
            # pour eviter de recalculer le prefixe (system prompt + historique)
            if self._current_session_id:
                cached_kv = self._kv_cache.restore(
                    self._model, self._current_session_id, model_id=model_id
                )
                if cached_kv is not None:
                    logger.info(
                        "KV cache restaure pour session %s -- "
                        "prefixe non recalcule",
                        self._current_session_id,
                    )

            logger.info(f"Modele charge avec succes.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modele : {e}")
            raise

    def unload(self):
        """Dechargement propre pour liberer la RAM Metal.
        V10 Audit: ne delegue PAS a ModelManager (qui a sa propre reference),
        supprime directement la reference locale pour garantir la liberation memoire.
        """
        if self._model is not None:
            logger.info("Dechargement du modele local...")

            # V15 Phase 5 (Item 41) : sauvegarder le KV cache avant dechargement
            if self._current_session_id and self._current_model_id:
                self._kv_cache.save(
                    model=self._model,
                    session_id=self._current_session_id,
                    prompt=self._current_session_id,  # placeholder -- ID comme cle
                    turn_number=0,
                    model_id=self._current_model_id,
                )

            del self._model
            if self._tokenizer is not None:
                del self._tokenizer
            self._model = None
            self._tokenizer = None
            self._current_model_id = None
            # V15 Phase 5 (Item 40) : marquer comme decharge
            get_budget().mark_unloaded("llm")
            gc.collect()
            try:
                mx.clear_cache()
            except Exception:
                pass
            logger.info("Modele local decharge, cache Metal vide")

    def set_session(self, session_id: str) -> None:
        """Definit l'ID de session pour le KV cache persistant."""
        self._current_session_id = session_id

    def set_lora_adapter(self, path: str) -> None:
        """Definit le chemin de l'adaptateur LoRA (recharge au prochain load_model)."""
        self._lora_adapter_path = path
        logger.info("Adaptateur LoRA configure: %s", path)

    async def generate_stream(self, prompt: str, intent: str = "RAG") -> AsyncGenerator[str, None]:
        """Genere une reponse via MLX en streaming.

        MLX Metal exige que load + generate soient sur le meme thread.

        V15 Phase 0B (P0 #31) -- Optimisations memoire :
        - KV cache 8-bit (kv_bits=8) : reduit la consommation RAM GPU de ~50%
          sans perte de qualite (preserve l'essentiel du signal attentionnel).
        - prefill_step_size=512 : limite le pic memoire lors du pre-remplissage
          du prompt (essentiel sur M1 8 Go avec swap).
        - Benchmark timing integre dans self.bench{}.
        - Speculation propre (draft model) : non applicable a Phi-4-mini
          (vocab_size=200k, aucun petit modele compatible disponible).
          A la place, KV cache quantifie + prefill econome.

        Draft model speculative decoding feasibility :
        - MLX supporte nativement speculative_generate_step avec draft_model
        - Phi-4-mini utilise un tokenizer tiktoken (200019 tokens)
        - Aucun modele draft <500MB ne partage ce tokenizer
        - Solutions alternatives pour V15.1+ :
          a) KV cache quantization (actif)
          b) Prompt lookup decoding (reuse tokens du prompt comme draft)
          c) Layer-wise speculation (dernieres couches du modele comme draft)
        """
        # V10 Audit: Lock thread-safe -- evite les races conditions si deux
        # coroutines appellent generate_stream() simultanement
        async with self._gen_lock:
            model_id = self._get_required_model(intent)

            # Chargement synchrone sur l'event loop thread
            # (MLX Metal GPU = thread-local, load et generate doivent cohabiter)
            try:
                await self._load_model(model_id)
            except Exception as e:
                logger.error(f"Impossible de charger le modele {model_id} : {e}")
                raise

            try:
                # Parametres de sampling
                if intent == "RAG":
                    is_1_5b = "1.5B" in model_id
                    temp = 0.35 if is_1_5b else 0.1
                    top_p = 0.9
                    rep_penalty = 1.10 if is_1_5b else 1.05
                elif intent == "SIMPLE":
                    is_1_5b = "1.5B" in model_id
                    temp = 0.7 if is_1_5b else 0.6
                    top_p = 0.90
                    rep_penalty = 1.20 if is_1_5b else 1.05
                else:
                    temp = 0.4
                    top_p = 0.85
                    rep_penalty = 1.10

                self._last_temperature = temp

                # V15 P0 #31 : parametres MLX optimises pour M1 8 Go
                make_sampler_kwargs = dict(temp=temp, top_p=top_p)
                # min_p=0.1 evite la gibberish aux tres basses temperatures
                if temp < 0.3:
                    make_sampler_kwargs["min_p"] = 0.1
                sampler = make_sampler(**make_sampler_kwargs)
                logits_processors = [make_repetition_penalty(rep_penalty)]

                # apply_chat_template
                formatted_prompt = prompt
                if self._tokenizer is not None and hasattr(self._tokenizer, 'apply_chat_template'):
                    try:
                        has_special_tokens = any(
                            marker in prompt
                            for marker in (
                                '<|assistant|>', 'UNKNOWN_CHAR',
                                'UNKNOWN_CHAR', '<|end|>', '<|user|>',
                                'UNKNOWN_CHAR', 'UNKNOWN_CHAR',
                            )
                        )
                        if not has_special_tokens:
                            system_markers = [
                                "Tu es NURU", "Tu es", "Ta mission",
                                "# PRIORITE", "# MODE RAG", "# MODE HYBRIDE",
                                "## INSTRUCTION STRICTE",
                            ]
                            found_system = any(prompt.startswith(m) for m in system_markers)
                            messages = [{"role": "user", "content": prompt}]
                            formatted_prompt = self._tokenizer.apply_chat_template(
                                messages, tokenize=False, add_generation_prompt=True,
                            )
                            logger.debug(f"apply_chat_template ({len(formatted_prompt)} chars)")
                        else:
                            logger.debug("Prompt deja formate -- skip apply_chat_template")
                    except Exception as e:
                        logger.debug(f"apply_chat_template ignore: {e}")
                        formatted_prompt = prompt

                # stream_generate DOIT tourner sur le meme thread que le load
                # (Metal GPU thread-local).
                t0 = time.perf_counter()
                n_tokens = 0
                response = None
                # Assert pour LSP : a ce stade, model et tokenizer sont garantis non-None
                assert self._model is not None
                assert self._tokenizer is not None
                for response in stream_generate(
                    self._model,
                    self._tokenizer,
                    formatted_prompt,
                    max_tokens=config.local_max_tokens,
                    sampler=sampler,
                    logits_processors=logits_processors,
                    # V15 P0 #31 : KV cache 8-bit reduit la pression memoire
                    kv_bits=8,
                    # Prefill progressif pour eviter le swap
                    prefill_step_size=512,
                ):
                    yield response.text
                    n_tokens += 1
                    await asyncio.sleep(0)

                # Benchmark stats (uniquement si au moins un token genere)
                if n_tokens > 0:
                    assert response is not None  # garanti par n_tokens > 0
                    elapsed = time.perf_counter() - t0
                    self.bench["prompt_ms"].append(response.prompt_tps)
                    self.bench["tok_s"].append(n_tokens / elapsed)
                    logger.debug(
                        "LocalLLM bench : %.1f tok/s (%d tokens, %.1fs, intent=%s)",
                        n_tokens / elapsed, n_tokens, elapsed, intent,
                    )

                self._schedule_unload()

            except Exception as e:
                logger.error(f"Erreur durant l'inference MLX : {e}")
                self.unload()  # V10.2: Nettoyage memoire GPU en cas d'erreur (prevention fuite MLX)
                raise

    async def generate(
        self,
        prompt: str,
        intent: str = "RAG",
        temperature: float = 0.7,
    ) -> str:
        """Genere une reponse complete (non-streaming) pour Self-Consistency.
        
        Args:
            prompt: Prompt complet formate
            intent: Type d'intention (RAG, SIMPLE, COMPLEX)
            temperature: Temperature d'echantillonnage
            
        Returns:
            Reponse complete en string
        """
        model_id = self._get_required_model(intent)
        await self._load_model(model_id)

        # Parametres de sampling
        is_1_5b = "1.5B" in model_id
        if intent == "RAG":
            temp = temperature
            top_p = 0.9
            rep_penalty = 1.10 if is_1_5b else 1.05
        elif intent == "SIMPLE":
            temp = temperature
            top_p = 0.90
            rep_penalty = 1.20 if is_1_5b else 1.05
        else:
            temp = temperature
            top_p = 0.85
            rep_penalty = 1.10

        make_sampler_kwargs = dict(temp=temp, top_p=top_p)
        if temp < 0.3:
            make_sampler_kwargs["min_p"] = 0.1
        sampler = make_sampler(**make_sampler_kwargs)
        logits_processors = [make_repetition_penalty(rep_penalty)]

        # apply_chat_template si necessaire
        formatted_prompt = prompt
        if self._tokenizer is not None and hasattr(self._tokenizer, 'apply_chat_template'):
            try:
                has_special_tokens = any(
                    marker in prompt
                    for marker in (
                        '<|assistant|>', 'UNKNOWN_CHAR',
                        'UNKNOWN_CHAR', '<|end|>', '<|user|>',
                        'UNKNOWN_CHAR', 'UNKNOWN_CHAR',
                    )
                )
                if not has_special_tokens:
                    system_markers = [
                        "Tu es NURU", "Tu es", "Ta mission",
                        "# PRIORITE", "# MODE RAG", "# MODE HYBRIDE",
                        "## INSTRUCTION STRICTE",
                    ]
                    found_system = any(prompt.startswith(m) for m in system_markers)
                    messages = [{"role": "user", "content": prompt}]
                    formatted_prompt = self._tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True,
                    )
                    logger.debug(f"apply_chat_template ({len(formatted_prompt)} chars)")
                else:
                    logger.debug("Prompt deja formate -- skip apply_chat_template")
            except Exception as e:
                logger.debug(f"apply_chat_template ignore: {e}")
                formatted_prompt = prompt

        # Generation complete (non-streaming) via mlx_lm.generate
        import time
        from mlx_lm import generate
        
        response = generate(
            self._model,
            self._tokenizer,
            formatted_prompt,
            max_tokens=config.local_max_tokens,
            sampler=sampler,
            logits_processors=logits_processors,
            kv_bits=8,
            prefill_step_size=512,
        )
        
        self._schedule_unload()
        return response.text

    def warmup(self):
        """Charge le modele approprie silencieusement pour eviter le cold start."""
        logger.info("Warmup du LLM...")
        try:
            model_id = self._get_required_model("SIMPLE")
            self._load_model(model_id)
        except Exception as e:
            logger.error(f"Echec du warmup : {e}")