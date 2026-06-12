import re
import logging
from typing import List

logger = logging.getLogger(__name__)

STOP_WORDS = {
    # French
    "de", "la", "le", "les", "est", "un", "une", "en", "que", "qui", "dans", "par", "pour", "sur", "avec", "du", "des", 
    "se", "ses", "sa", "son", "ce", "cette", "ces", "et", "ou", "mais", "donc", "car", "ni", "ne", "pas", "plus", "aux", 
    "au", "combien", "comment", "quel", "quelle", "quels", "quelles", "sans", "sous", "parce", "alors", "tout", "tous", 
    "toute", "toutes", "fait", "faire", "suis", "es", "sommes", "etes", "sont", "avoir", "etre", "a", "l", "d", "qu", "c",
    # English
    "the", "a", "an", "and", "or", "but", "for", "with", "in", "on", "at", "of", "to", "is", "are", "was", "were", "this", "that"
}

class QueryRewriter:
    """Réécriture de requête pour améliorer le recall RAG.
    Gère l'expansion sémantique, la normalisation et l'expansion LLM via Groq.
    """
    
    def __init__(self, cloud_llm=None):
        # Dictionnaire d'expansion sémantique orienté Agronomie/ONG & Informatique
        self.synonyms = {
            "leblanc": ["Leblanc Bahiga Mudarhi"],
            "iita": ["International Institute of Tropical Agriculture"],
            "fao": ["Food and Agriculture Organization", "Organisation des Nations Unies pour l'alimentation"],
            "beaccom": ["Bureau d Etudes d Appui Conseil et de Coordination des Operations de Microfinance", "ONG BEACCOM", "projet BEACCOM RIKOLTO agriculture RDC"],
            "rikolto": ["ONG Rikolto", "Rikolto RDC", "programme agriculture durable"],
            "yarid": ["YARID", "ONG YARID", "projet YARID agriculture"],
            "palabek": ["Palabek camp", "Palabek Uganda", "refugies Palabek"],
            "lubero": ["Lubero Nord-Kivu", "territoire Lubero"],
            "kananga": ["Kananga Kasai Central", "projet Kananga"],
            "mel": ["Monitoring Evaluation Learning", "Suivi Évaluation Apprentissage"],
            "semence": ["système semencier", "multiplication", "variété améliorée"],
            "sol": ["fertilité", "pédologie", "érosion", "dégradation"],
            "ong": ["organisation non gouvernementale", "partenaire au développement"],
            "usaid": ["United States Agency for International Development"],
            "climat": ["climato-adapté", "changement climatique", "adaptation"],
            "maïs": ["zea mays", "céréale"],
            "manioc": ["manihot esculenta", "tubercule"],
            # Compétences informatiques (V4)
            "informatique": ["programmation", "développement", "logiciel", "python", "javascript", "html", "css", "sql", "base de données"],
            "programmation": ["python", "javascript", "code", "développement logiciel", "script"],
            "développement": ["software", "web", "application", "programmation", "code"],
            "ordinateur": ["informatique", "digital", "numérique", "computer", "it"],
            "logiciel": ["software", "application", "outil informatique", "programme"],
            "python": ["langage de programmation", "script", "data science"],
            "javascript": ["js", "langage web", "frontend", "node"],
            "base de données": ["sql", "database", "data", "gestion de données"],
            "data": ["donnée", "analyse", "science des données"],
            "cv": ["curriculum vitae", "resume"],
            "compétence": ["skill", "savoir-faire", "expertise", "qualification"],
        }
        self.cloud = cloud_llm  # Instance optionnelle de CloudLLM pour l'expansion LLM

    def rewrite(self, query: str) -> str:
        """Transforme une requête utilisateur en requête optimisée pour le RAG."""
        original_query = query.lower().strip()
        words = re.findall(r'\w+', original_query)
        
        # 1. Extraction d'entités et expansion
        expanded_terms = []
        for word in words:
            if word in self.synonyms:
                expanded_terms.extend(self.synonyms[word])
        
        # 2. Construction de la requête enrichie
        # On garde les mots originaux et on ajoute les synonymes
        unique_terms = list(dict.fromkeys(words + expanded_terms))
        rewritten_query = " ".join(unique_terms)
        
        if rewritten_query != original_query:
            logger.info(f"Query Rewriting: '{original_query}' -> '{rewritten_query}'")
            
        return rewritten_query

    def expand_with_llm(self, query: str) -> str:
        """Utilise Groq (llama-3.3-70b-versatile) pour générer des termes de recherche
        supplémentaires et les ajouter à la requête, améliorant le recall RAG.

        Fonctionnement :
        - 1 appel LLM cloud non-streaming avec timeout 5s
        - Prompt simple demandant 3-5 synonymes/termes liés
        - En cas d'échec (timeout, erreur, pas de cloud), retourne la requête inchangée
          (fallback silencieux sur le rewritter basique existant)
        - Les synonymes statiques du rewritter sont TOUJOURS actifs (méthode rewrite())
        """
        if self.cloud is None:
            logger.debug("expand_with_llm: pas de cloud LLM configuré, skip")
            return query

        prompt = (
            "Génère 3 à 5 termes de recherche ou synonymes pertinents "
            f"pour cette question : {query}. "
            "Réponds uniquement avec les termes séparés par des virgules, sans numérotation."
        )

        try:
            response = self.cloud.generate(prompt, timeout=5.0)
            if not response or not response.strip():
                logger.debug("expand_with_llm: réponse vide du LLM, fallback")
                return query

            # Extraire les termes : on nettoie les tirets, astérisques, chiffres
            import re
            terms = re.split(r'[,;\n]+', response)
            clean_terms = []
            for term in terms:
                t = re.sub(r'^[\s*#\-\d\.\)]+', '', term).strip().lower()
                if t and len(t) > 2:  # Ignorer les fragments trop courts
                    clean_terms.append(t)

            if not clean_terms:
                logger.debug("expand_with_llm: aucun terme extrait, fallback")
                return query

            # Ajouter les termes LLM à la requête (après les synonymes)
            llm_terms_text = " ".join(clean_terms)
            expanded = f"{query} {llm_terms_text}"

            logger.info(
                f"LLM Query Expansion: '{query}' -> '{expanded}' "
                f"(termes ajoutés: {clean_terms})"
            )
            return expanded

        except Exception as e:
            logger.warning(
                f"expand_with_llm: échec ({type(e).__name__}: {e}), "
                "fallback sur requête inchangée"
            )
            return query

    def normalize_for_fts(self, query: str) -> str:
        """Prépare la requête pour FTS5 (Full Text Search) en éliminant les stop words."""
        # On garde les mots de plus de 3 lettres non présents dans les stop words
        words = [w for w in re.findall(r'\w{3,}', query.lower()) if w not in STOP_WORDS]
        if not words:
            # Fallback si tous les mots ont été éliminés
            words = re.findall(r'\w{3,}', query.lower())
        if not words:
            return query
        return " OR ".join([f'"{w}"' for w in words])

