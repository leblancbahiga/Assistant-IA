import asyncio
import logging
import os
import time
import gc
from pathlib import Path
from typing import Optional, AsyncGenerator
import mlx.core as mx
import sounddevice as sd
import numpy as np
import soundfile as sf
from src.config import config

logger = logging.getLogger(__name__)


# Détection du STT disponible
try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

try:
    import mlx_whisper
    HAS_MLX_WHISPER = True
except ImportError:
    HAS_MLX_WHISPER = False


class AudioEngine:
    """Moteur Audio unifié : STT (macOS native puis mlx-whisper fallback) et TTS (Piper/macOS say).

    Ordre de priorité STT :
    1. macOS Speech framework (via speech_recognition) — natif, offline, excellent français
    2. mlx-whisper — fallback si speech_recognition échoue
    Gère le Lazy Loading strict pour préserver la RAM.
    """

    def __init__(self):
        self._stt_model = None
        self._stt_model_size = None
        self._tts_voice = None
        self._is_speaking = False
        self._tts_lock = None
        self._sr_recognizer = None

    @property
    def tts_lock(self):
        if self._tts_lock is None:
            self._tts_lock = asyncio.Lock()
        return self._tts_lock

    # --- STT (Speech to Text) ---

    async def transcribe(self, audio_path: Path) -> str:
        """Transcrit un fichier audio. Tente macOS native d'abord, fallback mlx-whisper."""
        # Essai 1 : macOS Speech framework via speech_recognition
        if HAS_SPEECH_RECOGNITION:
            try:
                text = await self._transcribe_macos(audio_path)
                if text:
                    return text
            except Exception as e:
                logger.debug(f"macOS STT échoué: {e}")

        # Essai 2 : mlx-whisper (fallback)
        if HAS_MLX_WHISPER:
            try:
                return await self._transcribe_whisper(audio_path)
            except Exception as e:
                logger.error(f"mlx-whisper échoué: {e}")

        logger.error("Aucun moteur STT disponible")
        return ""

    async def _transcribe_macos(self, audio_path: Path) -> str:
        """Transcription via speech_recognition (backend Google Web Speech API gratuit)."""
        if self._sr_recognizer is None:
            self._sr_recognizer = sr.Recognizer()

        loop = asyncio.get_running_loop()

        def _do_transcribe():
            with sr.AudioFile(str(audio_path)) as source:
                audio = self._sr_recognizer.record(source)
            # Google Web Speech API : gratuit, sans clé, excellent pour le français
            return self._sr_recognizer.recognize_google(audio, language="fr-FR")

        text = await loop.run_in_executor(None, _do_transcribe)
        logger.info(f"📝 STT (Google Web Speech): {text[:60]}...")
        return text

    def _load_whisper(self):
        """Chargement Lazy de mlx-whisper."""
        if self._stt_model is None:
            model_size = config.stt_model
            logger.info(f"Chargement de mlx-whisper ({model_size})...")
            import mlx_whisper
            self._stt_model = mlx_whisper
            self._stt_model_size = model_size
            logger.info(f"STT {model_size} chargé.")

    async def _transcribe_whisper(self, audio_path: Path) -> str:
        """Transcription via mlx-whisper (fallback hors-ligne)."""
        self._load_whisper()
        try:
            loop = asyncio.get_running_loop()
            model_path = f"mlx-community/whisper-{self._stt_model_size}-mlx"
            result = await loop.run_in_executor(
                None, 
                lambda: self._stt_model.transcribe(
                    str(audio_path), path_or_hf_repo=model_path, language="fr"
                )
            )
            text = result.get("text", "").strip()
            logger.info(f"📝 STT (mlx-whisper): {text[:60]}...")
            return text
        finally:
            self.unload_stt()

    def unload_stt(self):
        """Libère mlx-whisper de la RAM."""
        if self._stt_model:
            self._stt_model = None
            gc.collect()
            mx.clear_cache()
            logger.info("STT déchargé.")

    # --- TTS (Text to Speech) ---
    def _load_tts(self):
        """Chargement Lazy de Piper."""
        if self._tts_voice is None and config.tts_engine == "piper":
            try:
                from piper import PiperVoice
                # Recherche du modèle onnx dans models/piper/
                model_path = config.model_dir / "piper" / "fr_FR-siwis-low.onnx"
                if model_path.exists():
                    logger.info(f"Chargement de Piper ({model_path.name})...")
                    self._tts_voice = PiperVoice.load(str(model_path))
                    logger.info("TTS Piper chargé.")
                else:
                    logger.warning(f"Modèle Piper introuvable à {model_path}. Fallback vers 'say'.")
            except Exception as e:
                logger.error(f"Erreur chargement Piper : {e}")

    async def speak(self, text: str):
        """Synthétise et joue le texte."""
        if not config.tts_enabled or not text:
            return

        async with self.tts_lock:
            self._load_tts()
            self._is_speaking = True
            
            try:
                if self._tts_voice:
                    # Utilisation de Piper
                    output_path = Path("/tmp/nuru_tts.wav")
                    with open(output_path, "wb") as f:
                        self._tts_voice.synthesize(text, f)
                    
                    # Lecture via sounddevice
                    data, fs = sf.read(output_path)
                    sd.play(data, fs)
                    sd.wait()
                else:
                    # Fallback macOS 'say'
                    process = await asyncio.create_subprocess_exec(
                        "say", "-v", "Thomas", text,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await process.wait()
            except Exception as e:
                logger.error(f"Erreur TTS : {e}")
            finally:
                self._is_speaking = False
                if self._tts_voice:
                    self.unload_tts()

    def unload_tts(self):
        """Libère Piper de la RAM."""
        if self._tts_voice:
            self._tts_voice = None
            gc.collect()
            mx.clear_cache()
            logger.info("TTS déchargé.")

    async def stop_speaking(self):
        """Arrête la lecture audio en cours."""
        if self._is_speaking:
            sd.stop()
            self._is_speaking = False
