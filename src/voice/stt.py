"""Pipeline STT — mlx-whisper tiny, streaming local, buffering intelligent.

Optimisé pour M1 8 Go : modèle tiny (~500 Mo RAM chargé),
déchargé quand inactif (RAM libérée).
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

from src.privacy.consent_layer import SensorType


class STTModelSize(enum.Enum):
    """Taille du modèle Whisper (compromis vitesse/précision)."""
    TINY = "tiny"         # ~500 Mo, ~100ms, recommandé M1 8 Go
    BASE = "base"         # ~700 Mo, ~200ms
    SMALL = "small"       # ~1.2 Go, ~400ms (trop lourd pour M1 8 Go)


@dataclass
class STTConfig:
    """Configuration du pipeline STT."""
    model_size: STTModelSize = STTModelSize.TINY
    language: str = "fr"
    sample_rate: int = 16000
    chunk_size_ms: int = 200
    silence_threshold_ms: int = 1500
    max_duration_seconds: int = 60
    enable_vad: bool = True
    device: str = "mps"
    compute_type: str = "float16"


@dataclass
class STTResult:
    """Résultat de la transcription."""
    text: str
    confidence: float
    duration_ms: float
    language: str
    segments: list[dict] = field(default_factory=list)
    is_final: bool = False

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "language": self.language,
            "is_final": self.is_final,
            "n_segments": len(self.segments),
        }


class SpeechToText:
    """Pipeline STT avec mlx-whisper.

    Usage :
        stt = SpeechToText()
        await stt.load()
        result = await stt.transcribe(audio_bytes)
        await stt.unload()
    """

    def __init__(self, config: Optional[STTConfig] = None, consent_layer=None):
        self.config = config or STTConfig()
        self._model: Any = None
        self._loaded = False
        self._on_result: Optional[Callable[[STTResult], None]] = None
        self._consent = consent_layer  # Injection DI ou lazy singleton

    @property
    def consent(self):
        """Accès paresseux au ConsentLayer."""
        if self._consent is None:
            from src.privacy import get_consent_layer
            self._consent = get_consent_layer()
        return self._consent

    async def load(self) -> bool:
        """Charge le modèle Whisper en mémoire.

        Vérifie le consentement micro avant activation.
        Retourne False si RAM insuffisante ou consentement refusé.
        """
        if self._loaded:
            return True

        # V15 P2 #25 : vérification consentement micro
        if not self.consent.request_access(
            SensorType.MICROPHONE,
            purpose="Transcription vocale",
            max_duration=self.config.max_duration_seconds,
        ):
            logger.warning("STT: accès micro refusé par consentement")
            return False

        try:
            import psutil

            available_gb = psutil.virtual_memory().available / (1024**3)
            if available_gb < 1.0:
                logger.warning("RAM insuffisante pour STT, skip")
                return False

            import mlx_whisper  # type: ignore
            self._model = mlx_whisper
            self._loaded = True
            logger.info(f"STT chargé : {self.config.model_size.value} ({self.config.device})")
            return True
        except ImportError:
            logger.warning("mlx-whisper non installé")
            return False
        except Exception as e:
            logger.error(f"Erreur chargement STT: {e}")
            return False

    async def unload(self) -> None:
        """Décharge le modèle et désactive le micro (consentement)."""
        if self._loaded:
            self.consent.deactivate(SensorType.MICROPHONE)
        self._model = None
        self._loaded = False
        logger.info("STT déchargé")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def transcribe(self, audio_data: bytes) -> STTResult:
        """Transcrit un fichier audio complet."""
        if not self._loaded or self._model is None:
            if not await self.load():
                return STTResult(text="", confidence=0.0, duration_ms=0, language="")
            if self._model is None:
                return STTResult(text="", confidence=0.0, duration_ms=0, language="")

        start = time.time()
        try:
            import numpy as np
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            result = self._model.transcribe(
                audio_array,
                path_or_hf_repo=f"mlx-community/whisper-{self.config.model_size.value}",
                language=self.config.language,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
            )

            duration_ms = (time.time() - start) * 1000
            return STTResult(
                text=result.get("text", ""),
                confidence=result.get("confidence", 0.0),
                duration_ms=duration_ms,
                language=result.get("language", self.config.language),
                segments=result.get("segments", []),
                is_final=True,
            )
        except Exception as e:
            logger.error(f"Erreur transcription: {e}")
            return STTResult(text="", confidence=0.0, duration_ms=0, language="")

    async def transcribe_stream(self, audio_generator):
        """Streaming transcription — générateur asynchrone."""
        if not self._loaded or self._model is None:
            if not await self.load():
                return
            if self._model is None:
                return

        buffer = []
        buffer_duration = 0

        async for chunk in audio_generator:
            buffer.append(chunk)
            buffer_duration += self.config.chunk_size_ms

            if buffer_duration >= 2000:
                audio_data = b"".join(buffer)
                result = await self.transcribe(audio_data)
                result.is_final = False
                if self._on_result:
                    self._on_result(result)
                yield result

        if buffer:
            audio_data = b"".join(buffer)
            result = await self.transcribe(audio_data)
            result.is_final = True
            yield result

    def set_callback(self, callback: Callable[[STTResult], None]) -> None:
        self._on_result = callback

    def estimate_ram(self) -> int:
        return {STTModelSize.TINY: 500, STTModelSize.BASE: 700, STTModelSize.SMALL: 1200}[self.config.model_size]
