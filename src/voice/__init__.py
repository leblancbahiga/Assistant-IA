"""NURU Voice Pipeline — Phase 2.

Pipeline vocal local optimisé M1 8 Go :
  - STT : mlx-whisper tiny (100ms, ~500 Mo RAM)
  - TTS : Kokoro local, fallback macOS say
  - Wake word : OpenWakeWord (1-2% CPU)
  - VAD : Silero VAD (détection activité vocale)
"""

from .stt import SpeechToText, STTConfig, STTResult
from .tts import TextToSpeech, TTSConfig, TTSVoice
from .wake_word import WakeWordDetector, WakeWordConfig
from .vad import VoiceActivityDetector, VADConfig

__all__ = [
    "SpeechToText", "STTConfig", "STTResult",
    "TextToSpeech", "TTSConfig", "TTSVoice",
    "WakeWordDetector", "WakeWordConfig",
    "VoiceActivityDetector", "VADConfig",
]
