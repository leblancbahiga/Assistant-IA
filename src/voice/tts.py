"""Pipeline TTS — Kokoro TTS local avec fallback macOS 'say'.

Stratégie M1 8 Go :
  - Kokoro : voix naturelle, ~300 Mo RAM, streaming sentence-by-sentence
  - Fallback 'say' : 0 Mo supplémentaire, voix synthétique macOS
  - Décision automatique selon RAM disponible
"""

from __future__ import annotations

import asyncio
import enum
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class TTSBackend(enum.Enum):
    """Backend TTS disponible."""
    KOKORO = "kokoro"       # Local, voix naturelle, ~300 Mo
    MACOS_SAY = "say"       # macOS natif, 0 Mo, voix synthétique
    NONE = "none"           # Aucun TTS disponible


@dataclass
class TTSVoice:
    """Configuration de voix."""
    name: str = "default"
    speed: float = 1.0
    pitch: float = 1.0
    language: str = "fr-FR"
    kokoro_voice: str = "af_bella"  # Voix Kokoro

    @classmethod
    def default_french(cls) -> TTSVoice:
        return cls(name="french_female", language="fr-FR", kokoro_voice="af_bella")

    @classmethod
    def default_english(cls) -> TTSVoice:
        return cls(name="english_female", language="en-US", kokoro_voice="af_bella")


@dataclass
class TTSConfig:
    """Configuration du pipeline TTS."""
    voice: TTSVoice = field(default_factory=TTSVoice.default_french)
    preferred_backend: TTSBackend = TTSBackend.KOKORO
    sentence_delay_ms: int = 50       # Pause entre phrases (streaming)
    max_sentence_length: int = 200    # Caractères max par phrase
    cache_dir: Optional[Path] = None  # Cache audio pour les phrases fréquentes
    ram_threshold_gb: float = 1.5     # Sous ce seuil → fallback 'say'


@dataclass
class TTSResult:
    """Résultat de synthèse vocale."""
    text: str
    duration_ms: float
    backend: str
    output_path: Optional[Path] = None
    is_partial: bool = False


class TextToSpeech:
    """Pipeline TTS avec fallback intelligent.

    Usage :
        tts = TextToSpeech()
        await tts.load()
        await tts.speak("Bonjour, je suis NURU")
        # Streaming :
        async for chunk in tts.speak_stream("Long texte..."):
            play_audio(chunk)
        await tts.unload()
    """

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self._backend = TTSBackend.NONE
        self._kokoro = None
        self._loaded = False
        self._on_phrase: Optional[Callable[[TTSResult], None]] = None

    async def load(self) -> bool:
        """Charge le backend TTS (Kokoro si RAM suffisante)."""
        if self._loaded:
            return True

        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024**3)

            if available_gb >= self.config.ram_threshold_gb:
                # Essayer Kokoro
                try:
                    from kokoro import KPipeline  # type: ignore
                    self._kokoro = KPipeline(lang_code=self.config.voice.language[:2])
                    self._backend = TTSBackend.KOKORO
                    self._loaded = True
                    logger.info("TTS: Kokoro chargé ✅")
                    return True
                except ImportError:
                    logger.warning("Kokoro non installé, fallback macOS 'say'")
            else:
                logger.info(f"RAM insuffisante pour Kokoro ({available_gb:.1f} Go < {self.config.ram_threshold_gb} Go)")

            # Fallback macOS say
            self._backend = TTSBackend.MACOS_SAY
            self._loaded = True
            logger.info("TTS: macOS 'say' activé")
            return True

        except Exception as e:
            logger.error(f"Erreur chargement TTS: {e}")
            self._backend = TTSBackend.MACOS_SAY
            self._loaded = True
            return True

    async def unload(self) -> None:
        """Décharge Kokoro et libère la RAM."""
        self._kokoro = None
        self._backend = TTSBackend.NONE
        self._loaded = False
        logger.info("TTS déchargé")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def active_backend(self) -> TTSBackend:
        return self._backend

    async def speak(self, text: str, output_path: Optional[Path] = None) -> TTSResult:
        """Synthétise et joue le texte."""
        return await asyncio.to_thread(self._speak_sync, text, output_path)

    def _speak_sync(self, text: str, output_path: Optional[Path] = None) -> TTSResult:
        """Synthèse synchrone (exécutée dans un thread)."""
        start = time.time()

        if self._backend == TTSBackend.KOKORO and self._kokoro:
            return self._kokoro_speak(text, output_path, start)

        elif self._backend == TTSBackend.MACOS_SAY:
            return self._say_speak(text, start)

        return TTSResult(text=text, duration_ms=0, backend="none")

    def _kokoro_speak(self, text: str, output_path: Optional[Path], start: float) -> TTSResult:
        """Synthèse via Kokoro."""
        if self._kokoro is None:
            return self._say_speak(text, start)

        try:
            import numpy as np
            import soundfile as sf

            gen = self._kokoro(text, voice=self.config.voice.kokoro_voice, speed=self.config.voice.speed)
            audio_parts = []
            for i, (gs, ps, audio) in enumerate(gen):
                if audio is not None and len(audio) > 0:
                    audio_parts.append(audio)

            if audio_parts:
                full_audio = np.concatenate(audio_parts)
                if output_path:
                    sf.write(str(output_path), full_audio, 24000)
                duration = (time.time() - start) * 1000
                return TTSResult(text=text, duration_ms=duration, backend="kokoro", output_path=output_path)
        except Exception as e:
            logger.error(f"Kokoro error: {e}, fallback 'say'")
            return self._say_speak(text, start)

        return TTSResult(text=text, duration_ms=0, backend="none")

    def _say_speak(self, text: str, start: float) -> TTSResult:
        """Synthèse via macOS 'say'."""
        try:
            subprocess.run(
                ["say", "-v", self.config.voice.name if self.config.voice.name != "default" else "Thomas",
                 "-r", str(int(175 * self.config.voice.speed)), text],
                timeout=30, capture_output=True,
            )
            duration = (time.time() - start) * 1000
            return TTSResult(text=text, duration_ms=duration, backend="macos_say")
        except subprocess.TimeoutExpired:
            logger.error("say: timeout")
            return TTSResult(text=text, duration_ms=30000, backend="macos_say")
        except Exception as e:
            logger.error(f"say: {e}")
            return TTSResult(text=text, duration_ms=0, backend="none")

    async def speak_stream(self, text: str):
        """Générateur asynchrone — streaming sentence-by-sentence."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for sentence in sentences:
            if not sentence.strip():
                continue
            if len(sentence) > self.config.max_sentence_length:
                # Découper les longues phrases
                parts = [sentence[i:i+self.config.max_sentence_length]
                         for i in range(0, len(sentence), self.config.max_sentence_length)]
                for part in parts:
                    result = await self.speak(part)
                    result.is_partial = True
                    if self._on_phrase:
                        self._on_phrase(result)
                    yield result
                    await asyncio.sleep(self.config.sentence_delay_ms / 1000)
            else:
                result = await self.speak(sentence)
                result.is_partial = True
                if self._on_phrase:
                    self._on_phrase(result)
                yield result
                await asyncio.sleep(self.config.sentence_delay_ms / 1000)

    def set_callback(self, callback: Callable[[TTSResult], None]) -> None:
        """Callback pour chaque phrase produite."""
        self._on_phrase = callback

    def estimate_ram(self) -> int:
        """Estimation RAM en Mo."""
        if self._backend == TTSBackend.KOKORO:
            return 300
        elif self._backend == TTSBackend.MACOS_SAY:
            return 0
        return 0
