import httpx
import logging
from typing import List, Dict, Optional
from src.config import config

logger = logging.getLogger(__name__)

class WebSearch:
    """Client pour la recherche Web via Brave ou Tavily."""
    
    def __init__(self):
        self.brave_key = config.brave_key
        self.tavily_key = config.tavily_key

    async def search(self, query: str, count: int = 5) -> str:
        """Exécute une recherche web et retourne un contexte formaté.
        Privilégie Tavily pour sa meilleure synthèse IA, sinon utilise Brave.
        Fallback automatique vers Brave si Tavily échoue.
        """
        result = ""
        
        if self.tavily_key:
            result = await self._search_tavily(query, count)
        
        # Fallback vers Brave si Tavily a échoué ou n'est pas configuré
        if not result and self.brave_key:
            logger.info("Fallback vers Brave Search...")
            result = await self._search_brave(query, count)
        
        if not result:
            logger.warning("Aucune clé API de recherche (Brave/Tavily) configurée ou toutes les recherches ont échoué.")
        
        return result

    async def _search_tavily(self, query: str, count: int) -> str:
        """Recherche via l'API Tavily (optimisée pour LLM)."""
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": count,
            "include_answer": True
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(f"Erreur Tavily ({response.status_code}): {response.text}")
                    return ""
                
                data = response.json()
                results = data.get("results", [])
                
                formatted = []
                if data.get("answer"):
                    formatted.append(f'<extrait source="Web: Tavily Summary">\n{data["answer"]}\n</extrait>')
                
                for res in results:
                    source_name = f"Web: {res['title'][:50]}"
                    formatted.append(f'<extrait source="{source_name}">\nURL: {res["url"]}\nContenu: {res["content"]}\n</extrait>')
                
                return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Exception Tavily : {e}")
            return ""

    async def _search_brave(self, query: str, count: int) -> str:
        """Recherche via l'API Brave."""
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.brave_key
        }
        params = {
            "q": query,
            "count": count,
            "search_lang": "fr"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code != 200:
                    return ""

                results = response.json().get("web", {}).get("results", [])
                if not results: return ""

                formatted = []
                for res in results:
                    source_name = f"Web: {res.get('title', 'Unknown')[:50]}"
                    formatted.append(f'<extrait source="{source_name}">\nURL: {res.get("url")}\nContenu: {res.get("description")}\n</extrait>')
                return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Exception Brave : {e}")
            return ""
