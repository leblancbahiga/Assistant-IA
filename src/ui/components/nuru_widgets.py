"""
NURU V8+ — Composants réutilisables du thème Aether Dashboard.

ConfidenceWidget, ModeBadge, CitationBadge, StrategyBadge,
MetricMiniBar, CircularGaugeWidget, MetricsPanel, TypingIndicator.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPen,
    QBrush,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)


# ── Constantes ────────────────────────────────────────────────────────────

STRATEGY_COLORS: dict[str, str] = {
    "LOCAL": "#9098b0",
    "RAG": "#1d9e75",
    "CLOUD": "#378add",
    "VERIFY": "#ef9f27",
    "PLAN": "#7f77dd",
}

CONFIDENCE_COLORS: dict[str, str] = {
    "high": "#639922",
    "mid": "#ef9f27",
    "low": "#e24b4a",
}

MODE_COLORS: dict[str, str] = {
    "LOCAL": "#9098b0",
    "RAG": "#1d9e75",
    "CLOUD": "#378add",
    "VERIFY": "#ef9f27",
    "PLAN": "#7f77dd",
}


# ── 1. ConfidenceWidget ──────────────────────────────────────────────────


class ConfidenceWidget(QWidget):
    """Barre de confiance RAG — label + progressbar + valeur.

    Dynamic property ``level`` (high|mid|low) utilisable en QSS.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._score: float = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._label = QLabel("Confiance")
        self._label.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: bold;")
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedHeight(4)
        self._bar.setFixedWidth(64)
        self._bar.setTextVisible(False)
        self._bar.setObjectName("ConfidenceBar")
        layout.addWidget(self._bar)

        self._value_label = QLabel("0%")
        self._value_label.setStyleSheet(
            "color: #639922; font-size: 9px; font-weight: bold;"
        )
        layout.addWidget(self._value_label)

        self.set_score(0.0)

    # ── dynamic property "level" pour QSS ──

    def _get_level(self) -> str:
        if self._score >= 0.75:
            return "high"
        if self._score >= 0.40:
            return "mid"
        return "low"

    level = property(_get_level)

    # ── API publique ──

    def set_score(self, score: float) -> None:
        """Met à jour le score (0.0 → 1.0) et applique la couleur."""
        self._score = max(0.0, min(1.0, score))
        self._bar.setValue(int(self._score * 100))

        level = self._get_level()
        color = CONFIDENCE_COLORS[level]
        self._value_label.setText(f"{int(self._score * 100)}%")
        self._value_label.setStyleSheet(
            f"color: {color}; font-size: 9px; font-weight: bold;"
        )

        # La dynamic property "level" est lue par QSS
        self.setProperty("level", level)
        # Force le rafraîchissement du QSS
        self.style().unpolish(self._bar)
        self.style().polish(self._bar)

    @property
    def score(self) -> float:
        return self._score


# ── 2. ModeBadge ─────────────────────────────────────────────────────────


class ModeBadge(QLabel):
    """Capsule de mode colorée — LOCAL, RAG, CLOUD, VERIFY, PLAN.

    Dynamic property ``mode`` pour QSS styling.
    """

    def __init__(self, mode: str = "LOCAL", parent: QWidget | None = None):
        super().__init__(mode, parent)
        self._mode = mode.upper()
        self.setProperty("mode", self._mode)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self.setMinimumWidth(56)
        self.setStyleSheet(self._compute_style())

    def set_mode(self, mode: str) -> None:
        """Change le mode et met à jour le style."""
        self._mode = mode.upper()
        self.setText(self._mode)
        self.setProperty("mode", self._mode)
        self.setStyleSheet(self._compute_style())
        self.style().unpolish(self)
        self.style().polish(self)

    def _compute_style(self) -> str:
        color = MODE_COLORS.get(self._mode, "#6b7280")
        return (
            f"background-color: rgba({self._hex_to_rgb(color)}, 0.12);"
            f"color: {color};"
            "font-size: 9px;"
            "font-weight: bold;"
            "border-radius: 11px;"
            "padding: 2px 12px;"
        )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"

    @property
    def mode(self) -> str:
        return self._mode


# ── 3. CitationBadge ─────────────────────────────────────────────────────


class CitationBadge(QLabel):
    """Badge source cliquable — affiche ``📄 {filename}``.

    Émet :py:attr:`clicked` avec le chemin source et le numéro de page.
    """

    clicked = Signal(str, int)  # (source_path, page)

    def __init__(
        self,
        source_path: str = "",
        page: int = 1,
        parent: QWidget | None = None,
    ):
        self._source_path = source_path
        self._page = page
        filename = source_path.split("/")[-1] if source_path else "source"
        display = f"📄 {filename}"
        super().__init__(display, parent)
        self.setToolTip(f"{source_path}  ·  p.{page}")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "background-color: rgba(6, 78, 59, 0.5);"
            "color: #22c55e;"
            "font-size: 9px;"
            "font-weight: bold;"
            "border-radius: 4px;"
            "padding: 2px 8px;"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self._source_path, self._page)
        super().mousePressEvent(event)

    def set_source(self, source_path: str, page: int = 1) -> None:
        """Met à jour la source affichée."""
        self._source_path = source_path
        self._page = page
        filename = source_path.split("/")[-1] if source_path else "source"
        self.setText(f"📄 {filename}")
        self.setToolTip(f"{source_path}  ·  p.{page}")


# ── 4. StrategyBadge ─────────────────────────────────────────────────────


class StrategyBadge(QFrame):
    """Badge stratégie dans les métriques — point coloré + nom + sous-texte.

    Couleurs selon le mode : LOCAL=#9098b0, RAG=#1d9e75, CLOUD=#378add,
    VERIFY=#ef9f27, PLAN=#7f77dd.
    """

    def __init__(
        self,
        strategy: str = "LOCAL",
        model: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._strategy = strategy.upper()
        # Court-circuiter le nom du modèle pour lisibilité
        short = model.replace("mlx-community/", "").replace("Qwen2.5-", "")
        short = short.replace("-Instruct", "").replace("-instruct", "").replace("-4bit", "")
        self._model = short
        self.setObjectName("StrategyBadge")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(10)
        layout.addWidget(self._dot)

        self._name_label = QLabel(self._strategy)
        self._name_label.setStyleSheet(
            "color: #e2e8f0; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self._name_label)

        self._model_label = QLabel(self._model)
        self._model_label.setStyleSheet("color: #6b7280; font-size: 9px;")
        self._model_label.setMaximumWidth(80)
        layout.addWidget(self._model_label)

        layout.addStretch()
        self._apply_style()

    def set_strategy(self, strategy: str, model: str = "") -> None:
        """Change la stratégie et le sous-texte modèle."""
        self._strategy = strategy.upper()
        # Court-circuiter le nom du modèle pour lisibilité
        short = model.replace("mlx-community/", "").replace("Qwen2.5-", "")
        short = short.replace("-Instruct", "").replace("-instruct", "").replace("-4bit", "")
        self._model = short
        self._name_label.setText(self._strategy)
        self._model_label.setText(self._model)
        self._apply_style()

    def _apply_style(self) -> None:
        color = STRATEGY_COLORS.get(self._strategy, "#6b7280")
        r, g, b = self._hex_to_rgb(color)
        self._dot.setStyleSheet(f"color: {color}; font-size: 8px;")
        self.setStyleSheet(
            f"#StrategyBadge {{"
            f"    background-color: rgba({r},{g},{b}, 0.10);"
            f"    border: 1px solid rgba({r},{g},{b}, 0.25);"
            f"    border-radius: 8px;"
            f"}}"
        )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @property
    def strategy(self) -> str:
        return self._strategy


# ── 5. MetricMiniBar ─────────────────────────────────────────────────────


class MetricMiniBar(QWidget):
    """Ligne métrique compacte avec nom, valeur et mini progressbar (3px).

    Dynamic property ``metric`` pour QSS.
    """

    def __init__(
        self,
        name: str = "",
        value: str = "",
        percent: float = 0.0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._percent = 0.0
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: bold;")
        layout.addWidget(self._name_label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedHeight(3)
        self._bar.setTextVisible(False)
        self._bar.setObjectName("MetricMiniBarInner")
        layout.addWidget(self._bar, 1)

        self._value_label = QLabel(value)
        self._value_label.setStyleSheet(
            "color: #e2e8f0; font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(self._value_label)

        self.setProperty("metric", name.lower().replace(" ", "_"))
        self.set_percent(percent)

    def set_percent(self, percent: float) -> None:
        """Met à jour la valeur de la barre (0.0 → 100.0)."""
        self._percent = max(0.0, min(100.0, percent))
        self._bar.setValue(int(self._percent))

    def set_value(self, value: str) -> None:
        """Met à jour le texte de la valeur."""
        self._value_label.setText(value)

    def set_name(self, name: str) -> None:
        """Change le nom de la métrique."""
        self._name_label.setText(name)

    @property
    def percent(self) -> float:
        return self._percent


# ── 6. CircularGaugeWidget ────────────────────────────────────────────────


class CircularGaugeWidget(QWidget):
    """Jauge RAM circulaire avec arc animé (QPainter).

    - Arc de fond #2e3347 (270 degrés, départ 225°)
    - Arc valeur animé (QTimer 16ms)
    - Texte central : valeur + sous-texte
    - Couleur : >75%=#ef9f27, <50%=#639922, sinon #7f77dd
    """

    ARC_SPAN = 270       # degrés
    ARC_START = 225      # degrés (top-left)
    ANIM_INTERVAL = 16   # ms (~60 fps)

    def __init__(
        self,
        size: int = 120,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedSize(size, size)

        self._target_value: float = 0.0   # 0.0 → 1.0
        self._display_value: float = 0.0  # valeur animée en cours
        self._value_text: str = "0"
        self._sub_text: str = "RAM"

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(self.ANIM_INTERVAL)
        self._anim_timer.timeout.connect(self._animate_step)

    # ── API publique ──

    def set_value(
        self,
        value: float,
        value_text: str | None = None,
        sub_text: str | None = None,
    ) -> None:
        """Anime la jauge vers la nouvelle valeur (0.0 → 1.0)."""
        self._target_value = max(0.0, min(1.0, value))
        if value_text is not None:
            self._value_text = value_text
        if sub_text is not None:
            self._sub_text = sub_text
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    # ── Animation ──

    def _animate_step(self) -> None:
        diff = self._target_value - self._display_value
        if abs(diff) < 0.005:
            self._display_value = self._target_value
            self._anim_timer.stop()
        else:
            self._display_value += diff * 0.15  # interpolation fluide
        self.update()

    # ── Couleur selon niveau ──

    def _value_color(self) -> str:
        if self._display_value > 0.75:
            return "#ef9f27"
        if self._display_value < 0.50:
            return "#639922"
        return "#7f77dd"

    # ── Dessin ──

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        s = self.width()
        thickness = 8
        margin = thickness + 4
        rect = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
        center = self.rect().center()

        # ── Fond : arc gris sombre (270°, départ 225°) ──
        pen_track = QPen(QColor("#2e3347"))
        pen_track.setWidth(thickness)
        pen_track.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_track)
        # drawArc utilise 1/16 de degré
        span_bg = int(self.ARC_SPAN * 16)
        start_bg = int(self.ARC_START * 16)
        painter.drawArc(rect, start_bg, span_bg)

        # ── Arc valeur avec gradient conique ──
        value_color = self._value_color()
        gradient = QConicalGradient(center, self.ARC_START + 90)
        gradient.setColorAt(0.0, QColor(value_color))
        gradient.setColorAt(0.5, QColor(self._lighten(value_color, 0.3)))
        gradient.setColorAt(1.0, QColor(value_color))

        pen_value = QPen(QBrush(gradient), thickness)
        pen_value.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_value)

        span_value = int(-self._display_value * self.ARC_SPAN * 16)
        start_value = int(self.ARC_START * 16)
        painter.drawArc(rect, start_value, span_value)

        # ── Texte central : valeur ──
        font_main = QFont("SF Mono", max(14, int(s / 5.2)))
        font_main.setBold(True)
        painter.setFont(font_main)
        painter.setPen(QColor("#FFFFFF"))

        fm = painter.fontMetrics()
        text_h = fm.height()

        value_rect = QRectF(0, s / 2 - text_h - 2, s, text_h + 4)
        painter.drawText(value_rect, Qt.AlignCenter, self._value_text)

        # ── Sous-texte ──
        font_sub = QFont("SF Mono", max(10, int(s / 11)))
        font_sub.setBold(False)
        painter.setFont(font_sub)
        painter.setPen(QColor("#6b7280"))

        sub_rect = QRectF(0, s / 2 + 4, s, int(s / 8))
        painter.drawText(sub_rect, Qt.AlignCenter, self._sub_text)

        painter.end()

    @staticmethod
    def _lighten(hex_color: str, factor: float = 0.3) -> str:
        """Éclaircit une couleur hexadécimale."""
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"


# ── 7. MetricsPanel ──────────────────────────────────────────────────────


class MetricsPanel(QWidget):
    """Panneau droit complet de télémétrie.

    Contient :
    - Titre "Télémétrie"
    - StrategyBadge (stratégie active)
    - CircularGaugeWidget (RAM)
    - 4 MetricMiniBar (LLM, RAG, Tokens, Traces)
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricsPanel")
        self.setFixedWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Titre ──
        title = QLabel("Télémétrie")
        title.setStyleSheet(
            "color: #6b7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # ── StrategyBadge ──
        self._strategy_badge = StrategyBadge("LOCAL", "")
        layout.addWidget(self._strategy_badge)

        # ── Gauge container ──
        gauge_container = QWidget()
        gauge_layout = QVBoxLayout(gauge_container)
        gauge_layout.setContentsMargins(0, 0, 0, 0)
        gauge_layout.setAlignment(Qt.AlignCenter)
        self._gauge = CircularGaugeWidget(size=130)
        gauge_layout.addWidget(self._gauge, 0, Qt.AlignCenter)
        layout.addWidget(gauge_container)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: rgba(30, 30, 58, 0.6);")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Métriques ──
        metrics_title = QLabel("MÉTRIQUES")
        metrics_title.setStyleSheet(
            "color: #6b7280; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        layout.addWidget(metrics_title)

        self._metrics: dict[str, MetricMiniBar] = {}

        for name, key, default_val in [
            ("LLM", "llm", "0 tok/s"),
            ("RAG", "rag", "0.00"),
            ("Tokens", "tokens", "-0%"),
            ("Traces", "traces", "0"),
        ]:
            bar = MetricMiniBar(name, default_val, 0.0)
            self._metrics[key] = bar
            layout.addWidget(bar)

        layout.addStretch()

    # ── API publique ──

    def set_strategy(self, strategy: str, model: str = "") -> None:
        """Change la stratégie active affichée."""
        self._strategy_badge.set_strategy(strategy, model)

    def set_ram(self, percent: float, used_gb: str = "0", total_gb: str = "") -> None:
        """Met à jour la jauge RAM avec animation."""
        display = f"{used_gb}G"
        sub = f"RAM  ·  {total_gb}" if total_gb else "RAM"
        self._gauge.set_value(percent / 100.0, display, sub)

    def set_rag_score(self, score: float, label: str = "") -> None:
        """Met à jour la barre métrique RAG."""
        bar = self._metrics.get("rag")
        if bar:
            bar.set_percent(score * 100)
            display = label or f"{score:.2f}"
            bar.set_value(display)

    def set_llm(self, tok_per_sec: float, total_tokens: int = 0, label: str = "") -> None:
        """Met à jour la barre métrique LLM (tok/s)."""
        bar = self._metrics.get("llm")
        if bar:
            pct = min(100.0, (total_tokens / 500.0) * 100.0) if total_tokens > 0 else 0.0
            bar.set_percent(pct)
            display = label or f"{tok_per_sec:.1f} tok/s"
            bar.set_value(display)

    def set_token_reduction(self, percent: float, label: str = "") -> None:
        """Met à jour la barre métrique Tokens (réduction de tokens)."""
        bar = self._metrics.get("tokens")
        if bar:
            safe = max(0.0, percent)
            bar.set_percent(abs(safe))
            display = label or f"{safe:.0f}%"
            bar.set_value(display)

    def set_traces(self, count: int, label: str = "") -> None:
        """Met à jour la barre métrique Traces."""
        bar = self._metrics.get("traces")
        if bar:
            # On mappe le nombre de traces sur un pourcentage relatif (max 500)
            pct = min(100.0, (count / 500.0) * 100.0)
            bar.set_percent(pct)
            display = label or str(count)
            bar.set_value(display)


# ── 8. TypingIndicator V8+ — Stratégie active + points animés ──────────────


class TypingIndicator(QFrame):
    """Indicateur de frappe V8+ — affiche la stratégie active + 3 points animés.

    - QTimer 400ms, phase 0-2
    - Dessin QPainter avec DOT_SIZE=4, DOT_GAP=4
    - Point actif se déplace de -2px vers le haut
    - Label de stratégie à gauche des points (ex: "RECHERCHE MULTI-STRATÉGIE · 2/3")
    - Style : fond #0D1720, bordure #1A2D40, bordure gauche #1A5F9A
    """

    DOT_SIZE = 4
    DOT_GAP = 4
    ANIM_INTERVAL = 400  # ms

    # P1-I : États de stratégie avec icônes et couleurs
    STRATEGY_STEPS = {
        "routing":      ("Routage",       "🔍", "#3b82f6"),
        "rag":          ("RAG",           "📚", "#818cf8"),
        "generation":   ("Génération",    "⚡", "#22c55e"),
        "fact_check":   ("Fact-check",    "✓", "#f59e0b"),
        "search":       ("Recherche Web", "🌐", "#3b82f6"),
        "memory":       ("Mémoire",       "🧠", "#a855f7"),
        "thinking":     ("Raisonnement",  "🤔", "#818cf8"),
        "completed":    ("Terminé",       "✅", "#22c55e"),
        "error":        ("Erreur",        "❌", "#ef4444"),
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TypingIndicator")
        self.setFixedHeight(32)
        self.setMinimumWidth(80)

        # Layout : label + stretch + dots
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # P1-I : Label de stratégie enrichi
        self._strategy_label = QLabel("🔍 Routage")
        self._strategy_label.setStyleSheet(
            "color: #3b82f6; font-size: 10px; font-weight: bold;"
            " letter-spacing: 0.04em; background: transparent;"
        )
        layout.addWidget(self._strategy_label)

        layout.addStretch()

        # Dots container (painted)
        self._dots_container = DotsWidget(self)
        self._dots_container.setFixedSize(44, 16)
        layout.addWidget(self._dots_container)

        self._phase: int = 0
        self._timer = QTimer(self)
        self._timer.setInterval(self.ANIM_INTERVAL)
        self._timer.timeout.connect(self._advance_phase)
        self._timer.start()

        # Style du frame
        self.setStyleSheet(
            "#TypingIndicator {"
            "  background-color: #0D1720;"
            "  border: 0.5px solid #1A2D40;"
            "  border-left: 2px solid #1A5F9A;"
            "  border-radius: 2px 10px 10px 10px;"
            "}"
        )

    def set_strategy_label(self, label: str) -> None:
        """Met à jour le texte de stratégie affiché."""
        self._strategy_label.setText(label)

    def set_strategy(self, key: str, detail: str = "") -> None:
        """P1-I : Met à jour l'état de stratégie avec icône et couleur.

        Args:
            key: Clé depuis STRATEGY_STEPS (routing, rag, generation, etc.)
            detail: Texte supplémentaire optionnel (ex: source courante)
        """
        if key in self.STRATEGY_STEPS:
            label_text, icon, color = self.STRATEGY_STEPS[key]
            text = f"{icon} {label_text}"
            if detail:
                text += f" · {detail}"
            self._strategy_label.setText(text)
            self._strategy_label.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold;"
                " letter-spacing: 0.04em; background: transparent;"
            )

    def _advance_phase(self) -> None:
        self._phase = (self._phase + 1) % 3
        self._dots_container.update()

    def stop(self) -> None:
        """Arrête l'animation."""
        self._timer.stop()
        self._phase = -1
        self._dots_container.update()

    def start(self) -> None:
        """(Re)démarre l'animation."""
        if not self._timer.isActive():
            self._phase = 0
            self._timer.start()

    # Remplacer paintEvent du frame par un paint sur le conteneur de points
    def paintEvent(self, event) -> None:
        # On délègue le dessin des points au conteneur via son paintEvent
        # Le QFrame gère déjà le style via QSS
        super().paintEvent(event)

    # Rendre le dots_container accessible pour le dessin
    def _dot_paint(self, painter: QPainter) -> None:
        if self._phase < 0:
            return

        painter.setRenderHint(QPainter.Antialiasing)

        dot_color = QColor("#00d4ff")
        dot_color_dim = QColor(0, 212, 255, 60)

        w = self._dots_container.width()
        h = self._dots_container.height()
        total_w = 3 * self.DOT_SIZE + 2 * self.DOT_GAP
        start_x = (w - total_w) // 2
        cy = h // 2

        for i in range(3):
            x = start_x + i * (self.DOT_SIZE + self.DOT_GAP)
            y_offset = -2 if i == self._phase else 0
            y = cy + y_offset - self.DOT_SIZE // 2

            if i == self._phase:
                painter.setBrush(QBrush(dot_color))
                painter.setPen(Qt.NoPen)
            else:
                painter.setBrush(QBrush(dot_color_dim))
                painter.setPen(Qt.NoPen)

            painter.drawEllipse(x, y, self.DOT_SIZE, self.DOT_SIZE)


class DotsWidget(QWidget):
    """Widget conteneur pour les points animés du TypingIndicator."""

    def __init__(self, parent_typing: TypingIndicator, parent: QWidget | None = None):
        super().__init__(parent)
        self._parent_typing = parent_typing
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self._parent_typing._dot_paint(painter)
        painter.end()
