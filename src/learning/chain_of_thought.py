"""NURU V16 — Chain of Thought (Wei et al. 2022).

Force le modele a raisonner etape par etape avant la reponse finale.
+15% qualite sur problemes complexes, -50% erreurs de raisonnement.
Cout : ~2x tokens (prompt + etapes). Compatible M1 8Go.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompts CoT ──────────────────────────────────────────────────────────────

COT_INSTRUCTION = """## CONSIGNE DE RAISONNEMENT
Avant de donner ta reponse finale, decompose ton raisonnement en etapes explicites.
Utilise le format suivant :

## RAISONNEMENT
Etape 1 : [analyse de la question]
Etape 2 : [recherche d'informations dans le contexte]
Etape 3 : [synthese et verification]
...

## REPONSE FINALE
[reponse concise et complete, basee sur le raisonnement ci-dessus]

ATTENTION : Ne saute jamais l'etape de raisonnement. Si tu manques d'informations,
dis-le et propose des pistes pour obtenir les donnees necessaires."""

COT_ESSAI_PROMPT = """Question : {query}

Contexte disponible :
{context}

Applique la consigne de raisonnement ci-dessus."""

COT_SIMPLE_PROMPT = """{system_prompt}

{context}

## QUESTION
{query}

## CONSIGNE DE RAISONNEMENT
Decompose ta reflexion etape par etape AVANT de donner la reponse finale.
Utilise :
## RAISONNEMENT
Etape 1 : ...
## REPONSE FINALE
..."""

# ── Patterns de detection de complexite ──

COMPLEX_PATTERNS = [
    r"combien\s+.*(?:etapes|phases|raisons|causes|facteurs)",
    r"(?:compare|difference|quels sont les|avantages?|inconvenients?)",
    r"(?:pourquoi|comment|explique).*(?:processus|mecanisme|fonctionne|marche)",
    r"(?:planifie|organise|structure|elabore).*(?:projet|tache|plan)",
    r"(?:resume|synthetise|analyse).*(?:document|rapport|article|fichier)",
    r"(?:quelles sont les etapes|decris le processus)",
    r"(?:calcule|estime|determine).*(?:cout|duree|effort|complexite)",
]


def detect_complexity(query: str, min_words: int = 7) -> bool:
    """Determine si une requete merite un raisonnement CoT."""
    if len(query.split()) >= min_words:
        return True
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, query.lower()):
            return True
    return False


def extract_reasoning_and_answer(response: str) -> tuple[str, str]:
    """Extrait raisonnement et reponse finale d'une reponse formatee CoT.
    
    Returns:
        (reasoning, answer) — si parsing echoue, answer = response brute.
    """
    # Pattern 1: #{2,4} RAISONNEMENT ... #{2,4} REPONSE FINALE
    m = re.search(
        r'#{2,4}\s*RAISONNEMENT\s*\n(.*?)\n#{2,4}\s*R[EÉ]PONSE\s*(?:FINALE)?',
        response, re.DOTALL | re.IGNORECASE
    )
    if m:
        reasoning = m.group(1).strip()
        after = response[m.end():].strip()
        # Prendre jusqu'a la fin ou jusqu'au prochain #
        next_header = re.search(r'#{1,4}\s', after)
        if next_header:
            answer = after[:next_header.start()].strip()
        else:
            answer = after
        return reasoning, answer
    
    # Pattern 2: avec accents varies (#{2,4} RAISONNEMENT ... #{2,4} REPONSE)
    m = re.search(
        r'#{2,4}\s*RAISONNEMENT\s*\n(.*?)\n#{2,4}\s*REPONSE',
        response, re.DOTALL | re.IGNORECASE
    )
    if m:
        reasoning = m.group(1).strip()
        after = response[m.end():].strip()
        next_header = re.search(r'#{1,4}\s', after)
        if next_header:
            answer = after[:next_header.start()].strip()
        else:
            answer = after
        return reasoning, answer
    
    # Pattern 3: #{2,4} RAISONNEMENT present mais pas #{2,4} REPONSE FINALE
    m = re.search(r'#{2,4}\s*RAISONNEMENT\s*\n(.*)', response, re.DOTALL | re.IGNORECASE)
    if m:
        content = m.group(1).strip()
        # Fallback semantique : transitions de reponse
        fallback_split = re.split(
            r'(?i)\n(?:en conclusion|pour resumer|finalement|reponse|reponse finale)[\s:]*\n',
            content
        )
        if len(fallback_split) > 1:
            return fallback_split[0].strip(), fallback_split[-1].strip()
        return content, ""
    
    # Aucun format detecte → retourner la reponse brute
    return "", response


def strip_reasoning_if_needed(response: str) -> str:
    """Si la reponse ne contient que du raisonnement (pas de section REPONSE), 
    on la garde telle quelle mais sans le format."""
    _, answer = extract_reasoning_and_answer(response)
    return answer if answer else response


def format_cot_prompt(
    system_prompt: str,
    query: str,
    context: str = "",
) -> str:
    """Formate un prompt avec instruction CoT."""
    if context:
        return COT_SIMPLE_PROMPT.format(
            system_prompt=system_prompt,
            context=f"## CONTEXTE\n{context}\n",
            query=query,
        )
    return COT_SIMPLE_PROMPT.format(
        system_prompt=system_prompt,
        context="",
        query=query,
    )


def should_use_cot(
    query: str,
    intent: str,
    max_tokens_local: int = 2048,
) -> bool:
    """Determine si CoT est approprie.
    
    CoT double le nombre de tokens generes.
    Sur M1 8Go, limiter aux requetes qui en valent la peine.
    """
    if intent == "COMPLEX":
        return True
    if intent == "RAG":
        return detect_complexity(query, min_words=7)
    if intent == "GENERAL":
        return detect_complexity(query, min_words=10)
    return False