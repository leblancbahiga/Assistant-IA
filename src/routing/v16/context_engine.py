"""NURU Router V16 — Niveau 4 : Context Engine.

Répond à l'audit §5 (aucune compréhension contextuelle) et à l'exemple :
    "Ouvre mon rapport."   → RAG, open_document = "rapport"
    "Résume-le."           → doit hériter RAG + le même document, sans
                              nouveau mot-clé documentaire dans la requête.

Le contexte est un état léger (pas un historique complet rejoué à chaque
tour — ça coûterait cher en RAM/CPU sur M1 8 Go). On garde seulement :
    - last_intent
    - last_document_ref   (nom de fichier / sujet ouvert)
    - turns_since_document (pour désactiver l'héritage après N tours neutres)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Requêtes courtes, sans objet explicite, qui font référence implicite au
# tour précédent (anaphore). Volontairement restreint pour éviter les faux
# positifs (une vraie question autonome ne doit jamais être aspirée ici).
ANAPHORA_PATTERNS = [
    r"^resume(-le|-la)?\s*$",
    r"^resume(-le|-la)?[\s,.]",
    r"^explique(-le|-la)?\s*$",
    r"^traduis(-le|-la)?\s*$",
    r"^corrige(-le|-la)?\s*$",
    r"^continue\s*$",
    r"^et ensuite\s*\??$",
    r"^plus de details?\s*\??$",
]
_ANAPHORA_RE = [re.compile(p) for p in ANAPHORA_PATTERNS]

DOCUMENT_OPEN_RE = re.compile(r"(ouvre|charge|lis)\s+(mon|ma|mes)?\s*(\S+)")

MAX_CONTEXT_AGE_TURNS = 3


@dataclass
class ConversationState:
    last_intent: str | None = None
    last_document_ref: str | None = None
    turns_since_document: int = 999

    def update_after_route(self, intent: str, folded_query: str) -> None:
        m = DOCUMENT_OPEN_RE.search(folded_query)
        if m:
            self.last_document_ref = m.group(3)
            self.turns_since_document = 0
        else:
            self.turns_since_document += 1
        self.last_intent = intent


@dataclass
class ContextBoost:
    intent: str | None = None
    weight: float = 0.0
    reasoning: str = ""


def resolve_context(folded_query: str, state: ConversationState) -> ContextBoost:
    if state.last_document_ref is None or state.turns_since_document > MAX_CONTEXT_AGE_TURNS:
        return ContextBoost()
    if any(p.match(folded_query) for p in _ANAPHORA_RE):
        return ContextBoost(
            intent="RAG",
            weight=7.0,
            reasoning=f"anaphore → héritage document '{state.last_document_ref}'",
        )
    return ContextBoost()
