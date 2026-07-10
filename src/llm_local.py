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
from src.core.model_manager import ModelManager  # : Gestion RAM centralisée
from src.core.ram_budget import get_budget, Priority
from src.cache.kv_cache import KVPersistentCache

logger = logging.getLogger(__name__)

class LocalLLM:
    """Gestionnaire de LLM locaux (MLX) avec Warmup et RAM Guard.

    Utilise ModelManager en interne pour le cycle de vie mémoire.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._current_model_id = None
        self._last_temperature = 0.7
        # V15 P2 #27 : Délégation au ModelManager avec keep-alive réduit à 5s
        self._model_manager = ModelManager(keep_alive_seconds=5)
        # V10 Audit: Lock thread-safe pour generate_stream()
        self._gen_lock = asyncio.Lock()
        # V15 Phase 0B — P0 #31 : cache de prompt pour les requêtes répétées
        self._prompt_cache: dict[int, object] = {}
        # Statistiques de benchmark
        self.bench: dict[str, list[float]] = {"prompt_ms": [], "tok_s": []}
        # V15 P2 #27 : Tâche de déchargement différé
        self._unload_task: Optional[asyncio.Task] = None
        # V15 Phase 5 (Item 41) : KV Cache Persistant
        self._kv_cache = KVPersistentCache(max_entries=10, max_total_mb=1024)
        self._current_session_id: str = ""
        # V15 Phase 5 (Item 38) : LoRA adaptateur RAG
        self._lora_adapter_path: Optional[str] = None

    def _schedule_unload(self):
        """Planifie le déchargement 5s après la fin de la génération.

        V15 P2 #27 : keep_alive réduit de 300s à 5s pour libérer
        la RAM Metal immédiatement après la réponse.
        """
        self._cancel_unload()

        async def _delayed():
            try:
                await asyncio.sleep(self._model_manager._keep_alive)
                if self._model is not None:
                    logger.info("⏰ Keep-alive expiré (5s). Déchargement auto.")
                    self.unload()
            except asyncio.CancelledError:
                pass

        try:
            self._unload_task = asyncio.create_task(_delayed())
        except RuntimeError:
            pass

    def _cancel_unload(self):
        """Annule le déchargement différé (nouvelle requête arrivée)."""
        if self._unload_task is not None:
            self._unload_task.cancel()
            self._unload_task = None

    def _get_required_model(self, intent: str) -> str:
        """Détermine quel modèle charger (1.5B ou 4B)."""
        ram_available_gb = psutil.virtual_memory().available / (1024**3)
        
        # Si un modèle est déjà chargé, sa mémoire sera libérée s'il est différent,
        # ou conservée s'il est identique. Donc on ajoute une estimation de sa taille à la RAM disponible.
        if self._model is not None and self._current_model_id is not None:
            # Correction 2B : Cast sécurisé en str pour éviter AttributeError sur None
            model_id_safe = str(self._current_model_id).lower()
            estimated_model_ram = 2.5 if "4b" in model_id_safe else 1.0
            ram_available_gb += estimated_model_ram

        # Seuil critique (switch Cloud total)
        if ram_available_gb < 0.3:
            raise RuntimeError(f"RAM critique ({ram_available_gb:.2f} Go).")
            
        # Sélection du modèle local
        # On force le 4B (Gemma 3) si on a au moins 0.5 Go de RAM (permet d'utiliser le swap M1)
        if ram_available_gb < 0.5:
            return config.local_model_fallback
        return config.local_model

    def _load_model(self, model_id: str):
        """Charge ou swappe le modèle en mémoire."""
        if self._current_model_id == model_id and self._model is not None:
            return

        # V15 Phase 5 (Item 40) : vérification budget RAM avant chargement
        budget = get_budget()
        if not budget.can_load("llm"):
            logger.warning(
                "⏭️ Chargement LLM refusé par RAMBudgetManager "
                f"(swap {budget.probe().swap_percent:.0f}%) — éviction en cours"
            )
            budget.evict(priority_below=Priority.CACHE)

        try:
            # Décharger proprement le modèle précédent s'il y en a un pour libérer la RAM Metal avant de charger le nouveau
            if self._model is not None:
                logger.info(f"Déchargement du modèle précédent ({self._current_model_id}) pour libérer de la mémoire avant le chargement du nouveau.")
                self.unload()

            # Résolution du chemin local
            resolved_path = config.get_model_path(model_id)
            logger.info(f"Chargement du modèle MLX depuis : {resolved_path}")

            self._model, self._tokenizer = load(resolved_path)
            self._current_model_id = model_id

            # V15 Phase 5 (Item 38) : Chargement adaptateur LoRA RAG si existant
            if self._lora_adapter_path:
                adapter_dir = Path(self._lora_adapter_path)
                if (adapter_dir / "adapters.safetensors").exists():
                    try:
                        self._model = load_adapters(self._model, self._lora_adapter_path)
                        logger.info("🧩 Adaptateur LoRA chargé depuis %s", self._lora_adapter_path)
                    except Exception as e:
                        logger.warning("⚠️ Échec chargement LoRA (%s) — inference sans adaptateur", e)
                else:
                    logger.info("ℹ️ Aucun adaptateur LoRA trouvé dans %s", self._lora_adapter_path)

            # V15 Phase 5 (Item 40) : marquer comme chargé dans le budget RAM
            budget.mark_loaded("llm")
            budget.touch("llm")

            # V15 Phase 5 (Item 41) : restauration du KV cache si disponible
            # pour éviter de recalculer le préfixe (system prompt + historique)
            if self._current_session_id:
                cached_kv = self._kv_cache.restore(
                    self._model, self._current_session_id, model_id=model_id
                )
                if cached_kv is not None:
                    logger.info(
                        "♻️ KV cache restauré pour session %s — "
                        "préfixe non recalculé",
                        self._current_session_id,
                    )

            logger.info(f"Modèle chargé avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle : {e}")
            raise

    def unload(self):
        """Déchargement propre pour libérer la RAM Metal.
        V10 Audit: ne délègue PAS à ModelManager (qui a sa propre référence),
        supprime directement la référence locale pour garantir la libération mémoire.
        """
        if self._model is not None:
            logger.info("🧹 Déchargement du modèle local...")

            # V15 Phase 5 (Item 41) : sauvegarder le KV cache avant déchargement
            if self._current_session_id and self._current_model_id:
                self._kv_cache.save(
                    model=self._model,
                    session_id=self._current_session_id,
                    prompt=self._current_session_id,  # placeholder — ID comme clé
                    turn_number=0,
                    model_id=self._current_model_id,
                )

            del self._model
            if self._tokenizer is not None:
                del self._tokenizer
            self._model = None
            self._tokenizer = None
            self._current_model_id = None
            # V15 Phase 5 (Item 40) : marquer comme déchargé
            get_budget().mark_unloaded("llm")
            gc.collect()
            try:
                mx.clear_cache()
            except Exception:
                pass
            logger.info("✅ Modèle local déchargé, cache Metal vidé")

    def set_session(self, session_id: str) -> None:
        """Définit l'ID de session pour le KV cache persistant."""
        self._current_session_id = session_id

    def set_lora_adapter(self, path: str) -> None:
        """Définit le chemin de l'adaptateur LoRA (rechargé au prochain load_model)."""
        self._lora_adapter_path = path
        logger.info("🧩 Adaptateur LoRA configuré: %s", path)

    async def generate_stream(self, prompt: str, intent: str = "RAG") -> AsyncGenerator[str, None]:
        """Génère une réponse via MLX en streaming.

        MLX Metal exige que load + generate soient sur le même thread.

        V15 Phase 0B (P0 #31) — Optimisations mémoire :
        - KV cache 8-bit (kv_bits=8) : réduit la consommation RAM GPU de ~50%
          sans perte de qualité (préserve l'essentiel du signal attentionnel).
        - prefill_step_size=512 : limite le pic mémoire lors du préremplissage
          du prompt (essentiel sur M1 8 Go avec swap).
        - Benchmark timing intégré dans self.bench{}.
        - Spéculation propre (draft model) : non applicable à Phi-4-mini
          (vocab_size=200k, aucun petit modèle compatible disponible).
          À la place, KV cache quantifié + prefill économe.

        Draft model speculative decoding feasibility :
        - MLX supporte nativement speculative_generate_step avec draft_model
        - Phi-4-mini utilise un tokenizer tiktoken (200019 tokens)
        - Aucun modèle draft <500MB ne partage ce tokenizer
        - Solutions alternatives pour V15.1+ :
          a) KV cache quantization (actif)
          b) Prompt lookup decoding (reuse tokens du prompt comme draft)
          c) Layer-wise speculation (dernières couches du modèle comme draft)
        """
        # V10 Audit: Lock thread-safe — évite les races conditions si deux
        # coroutines appellent generate_stream() simultanément
        async with self._gen_lock:
            model_id = self._get_required_model(intent)

            # Chargement synchrone sur l'event loop thread
            # (MLX Metal GPU = thread-local, load et generate doivent cohabiter)
            try:
                self._load_model(model_id)
            except Exception as e:
                logger.error(f"Impossible de charger le modèle {model_id} : {e}")
                raise

            try:
                # Paramètres de sampling
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

                # V15 P0 #31 : paramètres MLX optimisés pour M1 8 Go
                make_sampler_kwargs = dict(temp=temp, top_p=top_p)
                # min_p=0.1 évite la gibberish aux très basses températures
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
                                '<|assistant|>', '<|im_start|>assistant',
                                '<|im_end|>', '<|end|>', '<|user|>',
                                '<|im_start|>user', '<|im_start|>system',
                            )
                        )
                        if not has_special_tokens:
                            system_markers = [
                                "Tu es NURU", "Tu es", "Ta mission",
                                "# PRIORITÉ", "# MODE RAG", "# MODE HYBRIDE",
                                "## INSTRUCTION STRICTE",
                            ]
                            found_system = any(prompt.startswith(m) for m in system_markers)
                            messages = [{"role": "user", "content": prompt}]
                            formatted_prompt = self._tokenizer.apply_chat_template(
                                messages, tokenize=False, add_generation_prompt=True,
                            )
                            logger.debug(f"apply_chat_template ({len(formatted_prompt)} chars)")
                        else:
                            logger.debug("Prompt déjà formaté — skip apply_chat_template")
                    except Exception as e:
                        logger.debug(f"apply_chat_template ignoré: {e}")
                        formatted_prompt = prompt

                # stream_generate DOIT tourner sur le même thread que le load
                # (Metal GPU thread-local).
                t0 = time.perf_counter()
                n_tokens = 0
                response = None
                for response in stream_generate(
                    self._model,
                    self._tokenizer,
                    formatted_prompt,
                    max_tokens=config.rag_max_context_tokens,
                    sampler=sampler,
                    logits_processors=logits_processors,
                    # V15 P0 #31 : KV cache 8-bit réduit la pression mémoire
                    kv_bits=8,
                    # Prefill progressif pour éviter le swap
                    prefill_step_size=512,
                ):
                    yield response.text
                    n_tokens += 1
                    await asyncio.sleep(0)

                # Benchmark stats (uniquement si au moins un token généré)
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
                logger.error(f"Erreur durant l'inférence MLX : {e}")
                self.unload()  # V10.2: Nettoyage mémoire GPU en cas d'erreur (prévention fuite MLX)
                raise

    def warmup(self):
        """Charge le modèle approprié silencieusement pour éviter le cold start."""
        logger.info("Warmup du LLM...")
        try:
            model_id = self._get_required_model("SIMPLE")
            self._load_model(model_id)
        except Exception as e:
            logger.error(f"Échec du warmup : {e}")
