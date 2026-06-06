import httpx
import json
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional
from src.config import config

logger = logging.getLogger(__name__)

@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure: float = 0.0
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    timeout: float = 30.0  # secondes avant de réessayer

class CloudLLM:
    """Client API pour les modèles Cloud (DeepSeek, OpenRouter, Groq) avec Circuit Breaker."""

    def __init__(self):
        self.provider = config.cloud_provider
        self.model = config.cloud_model
        self.circuit_breaker = CircuitBreakerState()

    def generate(self, prompt: str, timeout: float = 5.0, model: Optional[str] = None) -> str:
        """Version synchrone NON-streaming pour expansion rapide de requête (QueryRewriter).

        Appel direct à l'API Groq avec timeout court. Supporte aussi les autres providers.
        Retourne le texte de la réponse ou lève une exception en cas d'échec.
        """
        provider = self.provider
        model = model or self.model

        if provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = config.groq_key
        elif provider == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
            api_key = config.deepseek_key
        elif provider == "openrouter":
            url = "https://api.openrouter.ai/api/v1/chat/completions"
            api_key = config.openrouter_key
        else:
            raise ValueError(f"Provider Cloud inconnu pour generate() synchrone : {provider}")

        if not api_key:
            raise ValueError(f"Clé API manquante pour {provider}")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 150,
            "stream": False,
        }

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        
    def _parse_provider_model(self, config_str: str, default_provider: str):
        """Parse 'provider/model_name' format."""
        parts = config_str.split('/', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return default_provider, config_str

    async def generate_stream(self, prompt: str, intent: str = "SIMPLE", system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Génère une réponse en streaming avec Circuit Breaker et Fallback automatique."""
        primary_provider = self.provider
        primary_model = self.model
        
        # 1. Tentative sur le Provider Primaire
        primary_failed = False
        
        if self.circuit_breaker.state == "OPEN":
            if time.time() - self.circuit_breaker.last_failure > self.circuit_breaker.timeout:
                self.circuit_breaker.state = "HALF_OPEN"
                logger.info("CloudLLM Circuit Breaker: HALF_OPEN (tentative de reconnexion au primaire)")
            else:
                logger.warning("CloudLLM Circuit Breaker: OPEN. Passage direct au Fallback.")
                primary_failed = True
                
        if not primary_failed:
            success = False
            try:
                async for chunk in self._do_stream(prompt, primary_provider, primary_model, system_prompt=system_prompt):
                    if not success:
                        success = True
                    yield chunk
                
                if success:
                    self.circuit_breaker.failures = 0
                    self.circuit_breaker.state = "CLOSED"
                    return
            except Exception as e:
                logger.error(f"Erreur avec le provider primaire {primary_provider}: {e}")
                self.circuit_breaker.failures += 1
                self.circuit_breaker.last_failure = time.time()
                if self.circuit_breaker.failures >= 3:
                    self.circuit_breaker.state = "OPEN"
        
        # 2. Tentative sur le Provider Fallback
        fallback_str = config.cloud_fallback
        if fallback_str:
            fallback_provider, fallback_model = self._parse_provider_model(fallback_str, "openrouter")
            logger.info(f"Tentative de fallback vers {fallback_provider} (modèle: {fallback_model})")
            
            try:
                # Indicateur visuel du fallback
                yield f" [⚠️ Bascule vers fallback: {fallback_provider}] "
                async for chunk in self._do_stream(prompt, fallback_provider, fallback_model, system_prompt=system_prompt):
                    yield chunk
            except Exception as e:
                logger.error(f"Erreur fatale Cloud LLM avec le fallback: {e}")
                yield f"\n[Erreur fatale Cloud LLM : Primaire et Fallback en échec. Raison: {e}]"
        else:
            yield "\n[Erreur : Cloud LLM temporairement indisponible et aucun fallback configuré.]"

    async def _do_stream(self, prompt: str, provider: str, model: str, system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Exécute l'appel réseau réel pour un provider donné (Groq, Gemini, Deepseek, OpenRouter)."""
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            api_key = config.groq_key
        elif provider == "gemini":
            # Gemini a un format d'URL différent avec la clé dans l'URL
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={config.gemini_key}"
            api_key = config.gemini_key
        elif provider == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
            api_key = config.deepseek_key
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            api_key = config.openrouter_key
        else:
            raise ValueError(f"Provider Cloud inconnu : {provider}")
            
        if not api_key:
            raise ValueError(f"Clé API manquante pour {provider}")
            
        if provider == "gemini":
            # Payload spécifique pour Gemini
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{prompt}" if system_prompt else prompt}]}
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1000
                }
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise Exception(f"Gemini Error {response.status_code}: {error_text.decode()}")
                    
                    async for line in response.aiter_lines():
                        if not line.strip(): continue
                        try:
                            # Gemini renvoie des morceaux de JSON dans une liste [...]
                            # Pour le streaming simple, on va parser ligne par ligne
                            if line.startswith("  "): # Indentation du JSON
                                data = json.loads(line.strip().rstrip(","))
                                if "candidates" in data:
                                    yield data["candidates"][0]["content"]["parts"][0]["text"]
                        except: continue
            return

        # OpenAI-Compatible providers (Groq, Deepseek, OpenRouter)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/nuru-assistant"
            headers["X-Title"] = "NURU V3"
            
        max_tokens = 1000
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": max_tokens
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_msg = error_text.decode('utf-8', errors='ignore')
                    raise Exception(f"HTTP {response.status_code}: {error_msg}")
                    
                async for line in response.aiter_lines():
                    if not line.strip() or line.strip() == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            delta = data["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError) as e:
                            logger.debug(f"Erreur parsing stream cloud : {e}")
                            continue