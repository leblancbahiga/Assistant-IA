"""NURU V10 — ArchitecturePage : schéma des composants NURU et état des modules.

Remplace l'ancien placeholder "Nuru Brain" par un aperçu concret.
Dynamique : imports réels, QTimer auto-refresh 5s, boutons Activer/Désactiver.
"""

from __future__ import annotations

import importlib
import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Définition des modules scrutés ──────────────────────────────────────
# (nom_logique, libellé_dans_ui, description_courte, import_path, class_name)
MODULE_DEFS = [
    (
        "orchestrator",
        "🎛️ Orchestrateur",
        "NuruOrchestrator — pipeline complet : RAG → LLM → "
        "FactCheck → Réflexion → Mémoire. Découplé V10.3.",
        "src.core.orchestrator",
        "NuruOrchestrator",
    ),
    (
        "rag_pipeline",
        "📚 Pipeline RAG",
        "RAGOrchestrator — retrieval, décomposition, "
        "Spotlight, scoring, vérification citations.",
        "src.orchestration.rag_pipeline",
        "RAGOrchestrator",
    ),
    (
        "llm_generator",
        "🧠 Générateur LLM",
        "LLMGenerator — cloud/local fallback, "
        "température adaptative, stratégie Archon.",
        "src.orchestration.llm_generator",
        "LLMGenerator",
    ),
    (
        "llm_cache",
        "💾 Cache LLM",
        "Multi-niveau : L1 RAM (256 entrées, TTL 5 min) "
        "+ L2 SQLite persistante. Promotion des hits.",
        "src.cache.llm_cache",
        "LLMCache",
    ),
    (
        "spotlight_search",
        "🔎 Recherche macOS",
        "Spotlight V2 — plein texte kMDItemTextContent, "
        "scoring par terme, 5 sous-termes max.",
        "src.rag.spotlight",
        "SpotlightSearch",
    ),
    (
        "trace_collector",
        "📊 Collecteur de traces",
        "TraceCollector — enregistrement asynchrone "
        "de chaque query, mode, confiance, latence.",
        "src.learning.trace_collector",
        "TraceCollector",
    ),
    (
        "feedback_collector",
        "💬 Feedback",
        "FeedbackCollector — thumbs up/down, corrections, "
        "notes 1–5, stockage SQLite.",
        "src.learning.feedback",
        "FeedbackCollector",
    ),
    (
        "guardrails",
        "🛡️ Guardrails",
        "PromptGuard — RAG_KEYWORDS, FallbackGuard, "
        "ResponseGuard, vérification evidence.",
        "src.core.response_guard",
        "StrictRAGGuard",
    ),
    (
        "memory_manager",
        "🧠 Mémoire",
        "MemoryManager V9 — 6 types de mémoire persistante. "
        "Requêtes récentes + contexte.",
        "src.memory.manager",
        "MemoryManager",
    ),
]


class ModuleCard(QFrame):
    """Carte représentant un module NURU avec son statut dynamique et un bouton toggle."""

    def __init__(
        self,
        name: str,
        description: str,
        available: bool = True,
        active: bool = True,
        details: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._module_name = name
        self._available = available
        self._active = active

        self.setObjectName("ModuleCard")
        self._update_stylesheet()

        layout = QHBoxLayout(self)
        layout.setSpacing(14)

        # Statut — icône dynamique
        self.badge = QLabel(self._status_icon())
        self.badge.setStyleSheet(
            f"font-size:22px;color:{self._status_color()};font-weight:700"
        )
        self.badge.setFixedWidth(30)
        layout.addWidget(self.badge, alignment=Qt.AlignTop)

        # Infos
        info = QVBoxLayout()
        info.setSpacing(4)

        title = QLabel(
            f"<span style='font-size:15px;font-weight:600;color:#e2f0f0'>{name}</span>"
        )
        info.addWidget(title)

        self.desc_label = QLabel(
            f"<span style='font-size:12px;color:#8899b0'>{description}</span>"
        )
        self.desc_label.setWordWrap(True)
        info.addWidget(self.desc_label)

        if details:
            details_label = QLabel(
                f"<span style='font-size:11px;color:#5a6a80'>{details}</span>"
            )
            details_label.setWordWrap(True)
            info.addWidget(details_label)

        layout.addLayout(info, stretch=1)

        # Bouton Activer / Désactiver
        self.toggle_btn = QPushButton(self._button_text())
        self.toggle_btn.setFixedWidth(110)
        self.toggle_btn.setEnabled(available)
        self._style_toggle_button()
        layout.addWidget(self.toggle_btn, alignment=Qt.AlignBottom)

    # ── API publique ─────────────────────────────────────────────────

    def update_status(self, available: bool, active: bool, details: str = ""):
        """Met à jour l'affichage après un check dynamique."""
        self._available = available
        self._active = active
        self.badge.setText(self._status_icon())
        self.badge.setStyleSheet(
            f"font-size:22px;color:{self._status_color()};font-weight:700"
        )
        self.toggle_btn.setEnabled(available)
        self.toggle_btn.setText(self._button_text())
        self._style_toggle_button()
        self._update_stylesheet()

    # ── Interne ──────────────────────────────────────────────────────

    def _status_icon(self) -> str:
        if not self._available:
            return "✗"
        return "✓" if self._active else "⚠️"

    def _status_color(self) -> str:
        if not self._available:
            return "#ef4444"  # rouge — indisponible
        return "#34d399" if self._active else "#fbbf24"  # vert / ambre

    def _button_text(self) -> str:
        return "Désactiver" if self._active else "Activer"

    def _style_toggle_button(self):
        if not self._available:
            self.toggle_btn.setStyleSheet(
                """
                QPushButton {
                    background: #374151;
                    color: #6b7280;
                    border: 1px solid #4b5563;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                }
                """
            )
        elif self._active:
            self.toggle_btn.setStyleSheet(
                """
                QPushButton {
                    background: #dc2626;
                    color: #fff;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #b91c1c;
                }
                """
            )
        else:
            self.toggle_btn.setStyleSheet(
                """
                QPushButton {
                    background: #16a34a;
                    color: #fff;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #15803d;
                }
                """
            )

    def _update_stylesheet(self):
        c = self._status_color()
        self.setStyleSheet(
            f"""
            ModuleCard {{
                background: rgba(20, 30, 50, 0.7);
                border: 1px solid {c}40;
                border-radius: 8px;
                padding: 14px;
            }}
            ModuleCard:hover {{
                border-color: {c}80;
                background: rgba(25, 38, 60, 0.8);
            }}
            """
        )


class ArchitecturePage(QWidget):
    """Page architecture NURU — dynamique avec QTimer + toggle modules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._module_enabled: dict[str, bool] = {}
        self._cards: dict[str, ModuleCard] = {}
        self._build_ui()
        # Auto‑refresh toutes les 5 secondes
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_modules)
        self._timer.start(5000)
        # Premier check immédiat
        self._check_modules()

    # ── API publique ─────────────────────────────────────────────────

    def set_enabled(self, module_name: str, enabled: bool):
        """Active ou désactive un module par son nom logique.

        Déclenche une mise à jour visuelle immédiate.
        """
        self._module_enabled[module_name] = enabled
        card = self._cards.get(module_name)
        if card is not None:
            card.update_status(
                available=True,
                active=enabled,
                details="Activé par l'utilisateur" if enabled else "Désactivé par l'utilisateur",
            )
        logger.info("Module %s → %s", module_name, "activé" if enabled else "désactivé")

    # ── Construction UI ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Titre
        title = QLabel("🏗️ Architecture NURU V10")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#e2f0f0")
        layout.addWidget(title)

        subtitle = QLabel(
            "Composants découplés — orchestrateur, RAG, LLM, cache, mémoire "
            "| auto‑refresh 5s"
        )
        subtitle.setStyleSheet("font-size:13px;color:#64748b;margin-bottom:8px")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none")
        container = QWidget()
        self._grid = QVBoxLayout(container)
        self._grid.setSpacing(10)

        # Création des cartes (état inconnu jusqu'au premier check)
        for logical_name, label, desc, *_ in MODULE_DEFS:
            card = ModuleCard(
                name=label,
                description=desc,
                available=False,
                active=False,
                details="détection en cours…",
            )
            card.toggle_btn.clicked.connect(
                lambda checked, m=logical_name: self._on_toggle(m)
            )
            self._cards[logical_name] = card
            self._grid.addWidget(card)

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    # ── Check modules dynamique ──────────────────────────────────────

    def _check_modules(self):
        """Tente d'importer chaque module et met à jour son statut."""
        for logical_name, label, desc, import_path, class_name in MODULE_DEFS:
            available = False
            details = ""
            try:
                mod = importlib.import_module(import_path)
                available = hasattr(mod, class_name)
                if available:
                    cls = getattr(mod, class_name)
                    details = f"{import_path}.{class_name} ✓"
                else:
                    details = f"classe {class_name} introuvable dans {import_path}"
            except (ImportError, ModuleNotFoundError) as exc:
                details = f"import échoué : {exc}"
            except Exception as exc:
                details = f"erreur : {exc}"

            # État activé par défaut si dispo, sinon respecte le dict interne
            if available:
                active = self._module_enabled.get(logical_name, True)
            else:
                active = False
                self._module_enabled[logical_name] = False

            card = self._cards.get(logical_name)
            if card is not None:
                card.update_status(
                    available=available,
                    active=active,
                    details=details,
                )

    # ── Toggle handler ────────────────────────────────────────────────

    def _on_toggle(self, logical_name: str):
        card = self._cards.get(logical_name)
        if card is None:
            return
        # Inverser l'état interne
        current = self._module_enabled.get(logical_name, True)
        new_state = not current
        self.set_enabled(logical_name, new_state)
