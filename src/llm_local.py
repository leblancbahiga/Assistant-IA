import mlx.core as mx
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler, make_repetition_penalty, make_logits_processors
import psutil
import logging
import gc
import asyncio
from typing import AsyncGenerator, Optional
from src.config import config
from src.core.model_manager import ModelManager  # V4.5 : Gestion RAM centralisée

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
        # V4.5 : Délégation au ModelManager
        self._model_manager = ModelManager(keep_alive_seconds=300)
        # V10 Audit: Lock thread-safe pour generate_stream()
        self._gen_lock = asyncio.Lock()

    def _schedule_unload(self):
        """Planifie le déchargement après keep_alive secondes d'inactivité."""
        self._model_manager.keep_alive()

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
            logger.info(f"Modèle chargé avec succès.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle : {e}")
            raise

    def unload(self):
        """Déchargement propre pour libérer la RAM Metal."""
        self._model_manager.unload()
        self._model = None
        self._tokenizer = None
        self._current_model_id = None

    async def generate_stream(self, prompt: str, intent: str = "RAG") -> AsyncGenerator[str, None]:
        """Génère une réponse via MLX en streaming.

        MLX Metal exige que load + generate soient sur le même thread.
        On charge d'abord (synchrone, même thread que l'event loop),
        puis on génère dans un thread pool avec son propre cycle load+generate.
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
                    top_p = 1.0
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
                sampler = make_sampler(temp=temp, top_p=top_p)
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
                            logger.debug(f"🧩 apply_chat_template ({len(formatted_prompt)} chars)")
                        else:
                            logger.debug("🧩 Prompt déjà formaté — skip apply_chat_template")
                    except Exception as e:
                        logger.debug(f"apply_chat_template ignoré: {e}")
                        formatted_prompt = prompt

                # stream_generate DOIT tourner sur le même thread que le load
                # (Metal GPU thread-local). Donc on l'appelle directement ici,
                # sur l'event loop thread. Le load a déjà été fait juste au-dessus.
                for response in stream_generate(
                    self._model,
                    self._tokenizer,
                    formatted_prompt,
                    max_tokens=config.rag_max_context_tokens,
                    sampler=sampler,
                    logits_processors=logits_processors,
                ):
                    yield response.text
                    await asyncio.sleep(0)

                self._schedule_unload()

            except Exception as e:
                logger.error(f"Erreur durant l'inférence MLX : {e}")
                raise

    def warmup(self):
        """Charge le modèle approprié silencieusement pour éviter le cold start."""
        logger.info("Warmup du LLM...")
        try:
            model_id = self._get_required_model("SIMPLE")
            self._load_model(model_id)
        except Exception as e:
            logger.error(f"Échec du warmup : {e}")
