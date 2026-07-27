import mlx.core as mx
import psutil
import logging
import gc
import asyncio
import concurrent.futures
import time
from pathlib import Path
from typing import AsyncGenerator, Optional
from src.config import config
from src.core.model_manager import ModelManager
from src.core.ram_budget import get_budget, Priority
# V16 AUDIT FIX QW14 : V12 kv_cache supprimé (code mort — MLX n'expose pas KV)

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
        # V15 P2 #27 : Delegation au ModelManager avec keep-alive (120s pour M1 8Go)
        self._model_manager = ModelManager(keep_alive_seconds=120)
        # V10 Audit: Lock thread-safe pour generate_stream()
        self._gen_lock = asyncio.Lock()
        # Statistiques de benchmark
        self.bench: dict[str, list[float]] = {"prompt_ms": [], "tok_s": []}
        # V15 P2 #27 : Tache de dechargement differe
        self._unload_task: Optional[asyncio.Task] = None
        # V16 AUDIT FIX QW14 : _current_session_id supprimé (KV cache mort)
        # V15 Phase 5 (Item 38) : LoRA adaptateur RAG
        self._lora_adapter_path: Optional[str] = None
        self._lora_loaded: bool = False  # V17 FIX : état réel du chargement LoRA
        # MLX single-thread executor: load + generate sur le meme thread
        # Necessite absolue sous Metal (thread-local streams et caches KV)
        self._mlx_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='mlx'
        )

    def _schedule_unload(self):
        """Planifie le dechargement différé après la fin de la génération.

        V16 FIX : keep_alive augmenté de 30s à 120s pour éviter rechargements
        intempestifs sur M1 8Go (swap lourd → reload plus coûteux que keep-warm).
        Le déchargement n'est pas une urgence RAM — l'embedder + reranker
        consomment moins que le LLM local et le swap fait tampon.
        """
        self._cancel_unload()

        async def _delayed():
            try:
                await asyncio.sleep(self._model_manager._keep_alive)
                if self._model is not None:
                    logger.info("Keep-alive expire (%ss). Déchargement auto.",
                                self._model_manager._keep_alive)
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
            # Vérification finale après éviction
            if not budget.can_load("llm"):
                swap_pct = budget.probe().swap_percent
                raise RuntimeError(
                    f"RAM insuffisante pour charger le LLM (swap={swap_pct:.0f}%). "
                    "Fermez d'autres applications et réessayez."
                )
            logger.info("RAM libérée après éviction, chargement autorisé")

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
                from mlx_lm.utils import load_adapters
                model, tokenizer = load(resolved_path)
                # V15 Phase 5 (Item 38) : Chargement LoRA sur le meme thread MLX
                lora_loaded = False
                if self._lora_adapter_path:
                    adapter_dir = Path(self._lora_adapter_path)
                    if (adapter_dir / "adapters.safetensors").exists():
                        try:
                            model = load_adapters(model, self._lora_adapter_path)
                            lora_loaded = True
                            logger.info("Adaptateur LoRA charge depuis %s", self._lora_adapter_path)
                        except Exception as e:
                            logger.warning("Echec chargement LoRA (%s) -- inference sans adaptateur", e)
                return model, tokenizer, lora_loaded

            try:
                self._model, self._tokenizer, self._lora_loaded = await asyncio.wait_for(
                    loop.run_in_executor(self._mlx_executor, _sync_load),
                    timeout=MODEL_LOAD_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout critique : Le chargement des poids MLX a pris plus de "
                    f"{MODEL_LOAD_TIMEOUT_SECONDS}s. Swap RAM sature sur M1 8Go. "
                    f"Fermez d'autres applications et reessayez."
                )
            
            self._current_model_id = model_id

            # ── Notify RAMBudgetManager ──
            # V15 Phase 5 (Item 40) : marquer comme charge dans le budget RAM
            budget.mark_loaded("llm")
            budget.touch("llm")

            # V16 AUDIT FIX QW14 : restore KV cache supprimé (code mort MLX)

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

            # V16 AUDIT FIX QW14 : save KV cache supprimé (code mort MLX)

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

    # V16 AUDIT FIX QW14 : set_session supprimé (KV cache mort)

    def set_lora_adapter(self, path: str) -> None:
        """Definit le chemin de l'adaptateur LoRA (recharge au prochain load_model)."""
        self._lora_adapter_path = path
        self._lora_loaded = False  # sera mis à True après load_model réussi
        logger.info("Adaptateur LoRA configure: %s", path)

    @property
    def lora_active(self) -> bool:
        """V17 FIX : état réel du LoRA — True si adaptateur chargé avec succès."""
        return self._lora_loaded and self._lora_adapter_path is not None

    async def generate_stream(self, prompt: str, intent: str = "RAG") -> AsyncGenerator[str, None]:
        """Genere une reponse via MLX en streaming sur le thread MLX dedie.

        MLX Metal exige que load + generate soient sur le meme thread.
        L'executeur dedie (self._mlx_executor) garantit cette contrainte.
        Les tokens sont renvoyes via asyncio.Queue depuis le thread MLX.
        """
        # V10 Audit: Lock thread-safe
        async with self._gen_lock:
            model_id = self._get_required_model(intent)

            try:
                await self._load_model(model_id)
            except Exception as e:
                logger.error(f"Impossible de charger le modele {model_id} : {e}")
                raise

            try:
                # Snapshots thread-safe pour le thread MLX dedie
                model = self._model
                tokenizer = self._tokenizer

                queue: asyncio.Queue = asyncio.Queue()
                t0 = time.perf_counter()

                def _sync_stream():
                    """Run MLX stream_generate on the dedicated executor thread."""
                    from mlx_lm import stream_generate
                    from mlx_lm.sample_utils import make_sampler, make_repetition_penalty
                    # V17 FIX : corriger les artefacts de tokenisation française
                    from src.french_tokenizer_fix import TokenizationFixStream
                    _fix_stream = TokenizationFixStream()

                    try:
                        # Parametres de sampling
                        if intent == "RAG":
                            is_1_5b = "1.5B" in model_id
                            temp = 0.35 if is_1_5b else 0.3
                            top_p = 0.9
                            rep_penalty = 1.10 if is_1_5b else 1.15
                        elif intent == "SIMPLE":
                            is_1_5b = "1.5B" in model_id
                            temp = 0.7 if is_1_5b else 0.6
                            top_p = 0.90
                            rep_penalty = 1.20 if is_1_5b else 1.05
                        else:
                            temp = 0.4
                            top_p = 0.85
                            rep_penalty = 1.10

                        make_sampler_kwargs = dict(temp=temp, top_p=top_p)
                        if temp < 0.3:
                            make_sampler_kwargs["min_p"] = 0.1
                        sampler = make_sampler(**make_sampler_kwargs)
                        logits_processors = [make_repetition_penalty(rep_penalty)]

                        # apply_chat_template
                        formatted_prompt = prompt
                        if tokenizer is not None and hasattr(tokenizer, 'apply_chat_template'):
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
                                    messages = [{"role": "user", "content": prompt}]
                                    formatted_prompt = tokenizer.apply_chat_template(
                                        messages, tokenize=False, add_generation_prompt=True,
                                    )
                            except Exception as e:
                                logger.warning(
                                    "⚠️ apply_chat_template a échoué — prompt brut utilisé: %s",
                                    e,
                                )

                        last_response = None
                        n_gen = 0
                        # V17: vide le cache Metal avant generation (evite GPU Timeout)
                        try:
                            import mlx.core as mx
                            if mx.metal.is_available():
                                mx.clear_cache()
                        except Exception:
                            pass
                        # V17: accumulation des token IDs pour decoder par lots
                        # (le decodeur gere les espaces correctement avec plus de contexte)
                        token_ids: list[int] = []
                        decoded_so_far = ""
                        for response in stream_generate(
                            model,
                            tokenizer,
                            formatted_prompt,
                            max_tokens=config.local_max_tokens,
                            sampler=sampler,
                            logits_processors=logits_processors,
                            kv_bits=8,
                            prefill_step_size=512,
                        ):
                            token_ids.append(response.token)

                            # Decoder le lot a chaque token et produire le diff
                            full_text = tokenizer.decode(token_ids)
                            new_text = full_text[len(decoded_so_far):]
                            if new_text:
                                decoded_so_far = full_text
                                # V17: retirer les balises de controle residuelles (<|end|>, <|assistant|>, etc.)
                                import re
                                new_text = re.sub(r"<\|[^|]+\|>", "", new_text)
                                if new_text:
                                    queue.put_nowait(new_text)

                            n_gen += 1
                            last_response = response

                        # ── Stats de benchmark ──
                        if last_response is not None:
                            queue.put_nowait({
                                "_bench": True,
                                "prompt_tps": last_response.prompt_tps,
                                "n_tokens": n_gen,
                                "temperature": temp,
                            })

                    except Exception as e:
                        queue.put_nowait({"_error": str(e)})
                    finally:
                        queue.put_nowait(None)  # sentinel

                loop = asyncio.get_event_loop()
                loop.run_in_executor(self._mlx_executor, _sync_stream)

                n_tokens = 0
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    if isinstance(item, dict):
                        if "_error" in item:
                            raise RuntimeError(item["_error"])
                        if "_bench" in item:
                            elapsed = time.perf_counter() - t0
                            self._last_temperature = item.get("temperature", 0.7)
                            prompt_tps = item["prompt_tps"]
                            tok_count = item["n_tokens"]
                            if tok_count > 0:
                                self.bench["prompt_ms"].append(prompt_tps)
                                self.bench["tok_s"].append(tok_count / elapsed)
                                logger.debug(
                                    "LocalLLM bench : %.1f tok/s (%d tokens, %.1fs, intent=%s)",
                                    tok_count / elapsed, tok_count, elapsed, intent,
                                )
                        continue
                    yield item
                    n_tokens += 1
                    # V16 FIX : éviter busy-wait 100% CPU (asyncio.sleep(0) reschedule immédiat)
                    if n_tokens % 10 == 0:
                        await asyncio.sleep(0)  # Tous les 10 tokens seulement

                self._schedule_unload()

            except Exception as e:
                logger.error(f"Erreur durant l'inference MLX : {e}")
                self.unload()  # V10.2: Nettoyage memoire GPU
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

        model = self._model
        tokenizer = self._tokenizer

        def _sync_generate():
            from mlx_lm import generate as mlx_generate
            from mlx_lm.sample_utils import make_sampler, make_repetition_penalty

            is_1_5b = "1.5B" in model_id
            if intent == "RAG":
                temp = temperature
                top_p = 0.9
                rep_penalty = 1.10 if is_1_5b else 1.15
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
            if tokenizer is not None and hasattr(tokenizer, 'apply_chat_template'):
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
                        messages = [{"role": "user", "content": prompt}]
                        formatted_prompt = tokenizer.apply_chat_template(
                            messages, tokenize=False, add_generation_prompt=True,
                        )
                except Exception:
                    pass

            response = mlx_generate(
                model, tokenizer, formatted_prompt,
                max_tokens=config.local_max_tokens,
                sampler=sampler,
                logits_processors=logits_processors,
                kv_bits=8,
                prefill_step_size=512,
            )
            return response

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._mlx_executor, _sync_generate)
        self._schedule_unload()
        return result

    def warmup(self):
        """Charge le modele approprie silencieusement pour eviter le cold start."""
        logger.info("Warmup du LLM...")
        try:
            model_id = self._get_required_model("SIMPLE")
            self._load_model(model_id)
        except Exception as e:
            logger.error(f"Echec du warmup : {e}")

    def close(self):
        """Libère les ressources : décharge le modèle + shutdown executor.
        
        V16 AUDIT FIX QW4 : shutdown du ThreadPoolExecutor pour éviter
        la fuite de threads à chaque hot-reload (-200 Mo/threads orphelins).
        """
        self.unload()
        self._mlx_executor.shutdown(wait=False, cancel_futures=True)
        logger.info("🔌 LocalLLM fermé : modèle déchargé, executor shutdown.")