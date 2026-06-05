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
    Gère l'expansion sémantique et la normalisation.
    """
    
    def __init__(self):
        # Dictionnaire d'expansion sémantique orienté Agronomie/ONG & Informatique
        self.synonyms = {
            "leblanc": ["Leblanc Bahiga Mudarhi"],
            "iita": ["International Institute of Tropical Agriculture"],
            "fao": ["Food and Agriculture Organization", "Organisation des Nations Unies pour l'alimentation"],
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

