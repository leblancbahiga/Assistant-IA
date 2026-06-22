"""VAD + Barge-in — Silero VAD pour interruption naturelle.

Détection d'activité vocale avec priorité à la voix utilisateur.
Permet d'interrompre NURU en parlant (barge-in).
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class VADState(enum.Enum):
    """État de l'activité vocale."""
    SILENCE = "silence"
    SPEECH = "speech"
    START_SPEECH = "start_speech"
    END_SPEECH = "end_speech"


@dataclass
class VADConfig:
    """Configuration VAD."""
    threshold: float = 0.5          # Seuil de détection parole (0-1)
    min_speech_duration_ms: int = 100   # Durée min pour confirmer parole
    min_silence_duration_ms: int = 800  # Durée min pour confirmer silence
    sample_rate: int = 16000
    frame_size_ms: int = 30         # Taille de fenêtre (30ms = standard Silero)
    enable_barge_in: bool = True    # Interruption vocale autorisée
    barge_in_threshold: float = 0.6 # Seuil pour interrompre


@dataclass
class VADResult:
    """Résultat de l'analyse VAD."""
    state: VADState
    probability: float          # Probabilité de parole (0.0–1.0)
    duration_ms: float          # Durée de l'état actuel
    is_barge_in: bool = False   # True = interruption détectée


class VoiceActivityDetector:
    """Détecteur d'activité vocale Silero VAD.

    Usage :
        vad = VoiceActivityDetector()
        await vad.load()
        async for result in vad.process_stream(audio_generator):
            if result.state == VADState.SPEECH:
                print("Parole détectée")
        await vad.unload()
    """

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self._model = None
        self._loaded = False
        self._current_state = VADState.SILENCE
        self._speech_start_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None
        self._on_state_change: Optional[Callable[[VADResult], None]] = None
        self._is_speaking = False  # NURU est-il en train de parler ? (pour barge-in)

    async def load(self) -> bool:
        """Charge Silero VAD."""
        if self._loaded:
            return True
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=True,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]
            self._loaded = True
            logger.info("Silero VAD chargé ✅")
            return True
        except Exception as e:
            logger.warning(f"Silero VAD non disponible: {e}")
            logger.info("VAD: mode simulé (toujours parole détectée)")
            self._loaded = True  # Mode dégradé — toujours actif
            return True

    async def unload(self) -> None:
        self._model = None
        self._loaded = False
        logger.info("VAD déchargé")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def set_nuru_speaking(self, speaking: bool) -> None:
        """Indique si NURU parle (pour barge-in)."""
        self._is_speaking = speaking

    async def process_stream(self, audio_generator):
        """Analyse un flux audio en continu.

        Yields:
            VADResult à chaque changement d'état
        """
        if not self._loaded:
            await self.load()

        frame_samples = int(self.config.sample_rate * self.config.frame_size_ms / 1000)

        async for audio_chunk in audio_generator:
            result = self._process_frame(audio_chunk)
            if result:
                yield result

    def _process_frame(self, audio_chunk: bytes) -> Optional[VADResult]:
        """Traite une frame audio et retourne le résultat si changement d'état."""
        try:
            import torch
            import numpy as np

            audio_tensor = torch.frombuffer(
                np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0,
                dtype=torch.float32,
            )

            if self._model:
                speech_prob = self._model(audio_tensor, self.config.sample_rate).item()
            else:
                # Mode dégradé : toujours 0.5
                speech_prob = 0.5

            now = time.time()
            is_speech = speech_prob >= self.config.threshold

            # Machine à états VAD
            if is_speech and self._current_state in (VADState.SILENCE, VADState.END_SPEECH):
                if self._speech_start_time is None:
                    self._speech_start_time = now
                elif (now - self._speech_start_time) * 1000 >= self.config.min_speech_duration_ms:
                    self._current_state = VADState.START_SPEECH
                    self._silence_start_time = None

                    is_barge_in = self._is_speaking and self.config.enable_barge_in

                    result = VADResult(
                        state=VADState.START_SPEECH,
                        probability=speech_prob,
                        duration_ms=(now - self._speech_start_time) * 1000,
                        is_barge_in=is_barge_in,
                    )
                    if self._on_state_change:
                        self._on_state_change(result)
                    return result

            elif not is_speech and self._current_state in (VADState.START_SPEECH, VADState.SPEECH):
                if self._silence_start_time is None:
                    self._silence_start_time = now
                elif (now - self._silence_start_time) * 1000 >= self.config.min_silence_duration_ms:
                    self._current_state = VADState.END_SPEECH
                    self._speech_start_time = None

                    result = VADResult(
                        state=VADState.END_SPEECH,
                        probability=speech_prob,
                        duration_ms=(now - self._silence_start_time) * 1000,
                    )
                    if self._on_state_change:
                        self._on_state_change(result)
                    return result

            # Mise à jour continue
            if is_speech:
                self._current_state = VADState.SPEECH
            else:
                self._current_state = VADState.SILENCE

            return None

        except Exception as e:
            logger.error(f"Erreur VAD: {e}")
            return None

    def set_callback(self, callback: Callable[[VADResult], None]) -> None:
        self._on_state_change = callback

    def estimate_ram(self) -> int:
        return 50  # Mo
