"""
Context Manager — Gestion budgétaire des tokens pour éviter overflow prompts.

Conçu pour Apple Silicon M1/M2 :
- Léger, pas de dépendances lourdes
- Estimation tokens par ÷4 (caractères FR)
- Priorisation systématique
"""
import logging

logger = logging.getLogger(__name__)

class ContextBudget:
    def __init__(self, max_prompt_tokens: int = 3000, reserved_response: int = 800):
        self.max_prompt = max_prompt_tokens
        self.max_prompt_tokens = max_prompt_tokens
        self.reserved_response = reserved_response
        self.available = max_prompt_tokens - reserved_response
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimation grossière : 1 token ≈ 4 caractères FR."""
        return len(text) // 4
    
    def _truncate_by_chars(self, text: str, max_chars: int) -> str:
        """Tronque par caractères en préservant les phrases."""
        if len(text) <= max_chars:
            return text
        # Trouver le dernier point avant la limite
        cut_point = text[:max_chars].rfind('.')
        if cut_point == -1:
            cut_point = max_chars
        return text[:cut_point + 1]
    
    def _format_history(self, history: list[dict]) -> str:
        lines = []
        for msg in history:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)
    
    def _build_prompt(self, system: str, rag: str, facts: str, history: str, include_system: bool = True, model_family: str = "phi") -> str:
        """Assemble le prompt final."""
        parts = []
        if include_system:
            parts.append(f"<|system|>\n{system}\n")
            if model_family == "phi":
                parts[-1] += "<|end|>\n"
            parts.append("<|user|>\n")
        
        if rag.strip():
            parts.append(f"## CONTEXTE DOCUMENTAIRE (SOURCES)\n{rag.strip()}\n")
        else:
            parts.append("## CONTEXTE DOCUMENTAIRE (SOURCES)\n[AUCUNE SOURCE DOCUMENTAIRE PERTINENTE TROUVÉE]\n")
            
        if history.strip():
            parts.append(f"## HISTORIQUE RÉCENT\n{history.strip()}\n")
            
        if not include_system:
             parts.append("\n--- FIN DU CONTEXTE ---\n")
             
        return "".join(parts)
    
    def allocate(self, system: str, rag: str, facts: list[str], history: list[dict], include_system: bool = True, model_family: str = "phi") -> str:
        """Construit le prompt dans le budget tokens."""
        # 1. Estimer le system prompt
        system_tokens = self._estimate_tokens(system)
        budget = self.available - (system_tokens if include_system else 0)
        
        if budget <= 0:
            logger.warning("System prompt trop long, troncature nécessaire")
            system = self._truncate_by_chars(system, self.available * 4)
            budget = 0
        
        # 2. RAG : priorité 80% du budget restant
        rag_budget = int(budget * 0.8)
        rag_text = "\n".join(rag) if isinstance(rag, list) else rag
        if self._estimate_tokens(rag_text) > rag_budget:
            rag_text = self._truncate_by_chars(rag_text, rag_budget * 4)
        
        # 3. Faits : 5% du budget
        facts_budget = int(budget * 0.05)
        facts_text = "\n".join(facts)
        if self._estimate_tokens(facts_text) > facts_budget:
            facts_text = self._truncate_by_chars(facts_text, facts_budget * 4)
        
        # 4. Historique : 15% du budget
        history_budget = int(budget * 0.15)
        history_text = self._format_history(history)
        if self._estimate_tokens(history_text) > history_budget:
            # Garder les 4 derniers échanges
            history = history[-4:]
            history_text = self._format_history(history)
            if self._estimate_tokens(history_text) > history_budget:
                history_text = self._truncate_by_chars(history_text, history_budget * 4)
        
        # 5. Assemblage
        prompt = self._build_prompt(system, rag_text, facts_text, history_text, include_system=include_system, model_family=model_family)
        
        # 6. Vérification finale
        total = self._estimate_tokens(prompt)
        if total > self.available:
            logger.warning(f"Prompt final trop long ({total} tokens), hard truncate")
            prompt = self._truncate_by_chars(prompt, self.available * 4)
        
        return prompt
