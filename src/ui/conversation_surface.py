"""NURU V12 — ConversationSurface (DM-1 "Deep Cyan").

Zone de chat avec bulles alignées :
- Utilisateur : droite, fond accent cyan transparent
- NURU : gauche, fond surface
- Markdown supporté pour les réponses NURU
- Streaming temps réel (token par token)
"""

import logging
import time

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QFont, QTextCursor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
    QHBoxLayout, QFrame, QTextBrowser, QGraphicsOpacityEffect,
)

from src.ui.tokens import Color, Typography, Radius, Spacing

logger = logging.getLogger(__name__)


class BubbleWidget(QFrame):
    """Bulle de chat — DM-1 : coins arrondis 12px, fond cyan ou surface."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self._is_user = is_user

        # DM-1 couleurs
        if is_user:
            bg = "rgba(0, 212, 255, 0.15)"
            text_color = Color.TEXT_PRIMARY
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.SM}px {Radius.LARGE}px"
        else:
            bg = "rgba(18, 30, 55, 0.80)"
            text_color = Color.TEXT_PRIMARY
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.LARGE}px {Radius.SM}px"

        self.setStyleSheet(f"""
            BubbleWidget {{
                background-color: {bg};
                border-radius: {radius};
                padding: {Spacing.SM}px;
            }}
        """)
        self.setMaximumWidth(900)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(4)

        if is_user:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {text_color}; font-size: {Typography.SIZE_BODY + 1}px;"
                f" font-family: {Typography.FAMILY_BODY}; background: transparent;"
            )
            layout.addWidget(label)
        else:
            self._browser = QTextBrowser()
            self._browser.setHtml(self._md_to_html(text))
            self._browser.setOpenExternalLinks(True)
            self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setStyleSheet(f"""
                QTextBrowser {{
                    background: transparent;
                    color: {text_color};
                    font-size: {Typography.SIZE_BODY + 1}px;
                    font-family: {Typography.FAMILY_BODY};
                    border: none;
                    padding: 0;
                }}
                QTextBrowser a {{ color: {Color.CYAN}; }}
            """)
            self._browser.document().setDocumentMargin(0)
            self._browser.setMinimumHeight(20)
            doc = self._browser.document()
            doc.setTextWidth(self._browser.viewport().width() - 4)
            layout.addWidget(self._browser)

        # ── Bandeau de confiance (caché par défaut, réservé assistant) ──
        self._bandeau = QFrame()
        self._bandeau.setObjectName("ConfidenceBandeau")
        self._bandeau.setVisible(False)
        layout.addWidget(self._bandeau)

    def set_metadata(self, metadata: dict) -> None:
        """Affiche le bandeau de confiance avec les métadonnées de la réponse."""
        if self._is_user:
            return

        # Extraire les données depuis event_data ou ragg_data
        rag = metadata.get("rag_result", {})
        if not rag or not isinstance(rag, dict):
            rag = metadata.get("rag_data", {})

        score = rag.get("top_score", metadata.get("rag_score", 0.0))
        sources = rag.get("sources", metadata.get("sources", []))
        documents_found = rag.get("documents_found", len(sources))
        chunks_retrieved = rag.get("chunks_retrieved", 0)
        retrieval_ms = rag.get("retrieval_time_ms", 0.0)
        confidence = metadata.get("confidence", 0.0)

        # Mode de routage
        intent = metadata.get("intent", "")
        mode_emoji = {"rag": "🔍", "local": "🧠", "cloud": "☁️", "hybrid": "🔄", "conversation": "💬", "chat": "💬"}

        # Construire le contenu
        parts = []

        # Barre de confiance
        if score > 0:
            pct = min(int(score * 100), 100)
            bar_chars = "█" * (pct // 10) + "░" * (10 - pct // 10)
            if pct >= 70:
                bar_color = "#00F0FF"
            elif pct >= 40:
                bar_color = "#FFB800"
            else:
                bar_color = "#FF3366"
            parts.append(f'<span style="color:{bar_color};font-weight:600;">{bar_chars} {pct}%</span>')

        # Sources
        if documents_found > 0:
            parts.append(f'<span style="color:#9BA5B5;">📄 {documents_found} source{"s" if documents_found > 1 else ""}</span>')

        # Mode
        if intent:
            emoji = mode_emoji.get(intent, "🔧")
            parts.append(f'<span style="color:#9BA5B5;">{emoji} {intent.title()}</span>')

        # Temps de retrieval
        if retrieval_ms > 0:
            parts.append(f'<span style="color:#6B7280;">⚡ {retrieval_ms:.0f}ms</span>')

        if not parts:
            self._bandeau.setVisible(False)
            return

        html = "  ·  ".join(parts)

        # Style du bandeau
        self._bandeau.setStyleSheet(f"""
            #ConfidenceBandeau {{
                background: transparent;
                border: none;
                border-top: 1px solid rgba(128, 128, 128, 0.15);
                padding: 4px 0 0 0;
                margin: 6px 0 0 0;
            }}
        """)
        layout = self._bandeau.layout() or QVBoxLayout(self._bandeau)
        layout.setContentsMargins(0, 4, 0, 0)

        # Nettoyer les anciens labels
        while layout.count():
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        label = QLabel(html)
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet(
            "background: transparent; color: #9BA5B5; font-size: 10px;"
            " font-family: 'SF Mono', 'JetBrains Mono', monospace; letter-spacing: 0.03em;"
        )
        layout.addWidget(label)
        self._bandeau.setVisible(True)

    def append_html(self, html_fragment: str):
        """Ajoute du HTML à la bulle existante (streaming)."""
        cursor = self._browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_fragment)
        # Auto-scroll au contenu le plus récent
        scrollbar = self._browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _md_to_html(self, md: str) -> str:
        """Conversion markdown minimal en HTML."""
        import re
        html = md
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:rgba(5,8,15,0.6);padding:10px 14px;'
            r'border-radius:8px;border:1px solid rgba(0,240,255,0.08);'
            r'font-family:JetBrains Mono;font-size:11px;overflow-x:auto;'
            r'color:#00F0FF;margin:6px 0;">\2</pre>',
            html, flags=re.DOTALL
        )
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:rgba(5,8,15,0.5);padding:2px 6px;'
            r'border-radius:4px;border:1px solid rgba(0,240,255,0.08);'
            r'font-family:JetBrains Mono;font-size:11px;'
            r'color:#7C3AED;">\1</code>',
            html
        )
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        html = html.replace('\n', '<br>')
        return html


class ConversationSurface(QWidget):
    """Zone de conversation scrollable — DM-1.

    Alignement :
      - Messages utilisateur → droite
      - Messages NURU → gauche
    """

    # V17.2 (audit F-6) : signal émis quand un fichier est déposé
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConversationSurface")
        self.setAcceptDrops(True)  # V17.2 : drag & drop activé
        self.setStyleSheet(f"""
            #ConversationSurface {{
                background-color: rgba(8, 14, 28, 0.55);
                border: 1px solid rgba(0, 240, 255, 0.06);
                border-radius: {Radius.LARGE}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # ── Indicateur de stratégie pipeline (caché par défaut) ──
        self._strategy_label = QLabel()
        self._strategy_label.setAlignment(Qt.AlignCenter)
        self._strategy_label.setStyleSheet(
            "background: transparent; color: #4A5568; font-size: 11px;"
            " font-weight: 500; letter-spacing: 0.04em; padding: 4px 0;"
        )
        self._strategy_label.setVisible(False)
        layout.addWidget(self._strategy_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {Color.BG_SURFACE1};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0, 212, 255, 0.20);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(0, 212, 255, 0.40);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(Spacing.SM)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)

        # État de streaming
        self._streaming_bubble: BubbleWidget | None = None
        self._last_assistant_bubble: BubbleWidget | None = None
        self._stream_buffer: list[str] = []
        self._stream_timer: QTimer | None = None
        # V17 Phase 2 : timer progressif (⏱ X.Xs) pendant le streaming
        self._stream_start_time: float = 0.0
        self._progress_timer: QTimer | None = None
        self._time_label = QLabel()
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setStyleSheet(
            "background: transparent; color: #4A5568; font-size: 10px;"
            " padding: 2px 0;"
        )
        self._time_label.setVisible(False)
        # Insérer le time_label APRÈS le strategy_label (index 1 dans le layout)
        self._time_label_pos = layout.count()  # index après strategy_label
        layout.insertWidget(self._time_label_pos, self._time_label)
        # Glue spaces entre tokens pour providers qui strippent
        # les espaces en début de token (openrouter deepseek, etc.)
        self._glue_spaces: bool = True

    # ── V17.2 (audit F-6) : Drag & drop de fichiers ──

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepte le drag si des fichiers locaux sont présents."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Émet file_dropped pour chaque fichier déposé."""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self.file_dropped.emit(path)
        event.acceptProposedAction()

    # ── Messages normaux ──

    def add_message(self, text: str, is_user: bool = False):
        """Ajoute un message complet (non streamé)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        bubble = BubbleWidget(text, is_user=is_user)

        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
            self._last_assistant_bubble = bubble
            self._fade_in_widget(bubble, 250)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, container
        )

        QTimer.singleShot(50, self._scroll_to_bottom)

    # ── Streaming ──

    def start_stream(self) -> None:
        """Crée une bulle vide pour le streaming de la réponse NURU.
        Lance le timer progressif ⏱.
        """
        # Vider le buffer
        self._stream_buffer = []

        # Forcer l'affichage immédiat du chunk précédent s'il y en a un
        self._flush_stream_buffer()

        # Créer une bulle vide
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self._streaming_bubble = BubbleWidget("", is_user=False)
        self._last_assistant_bubble = self._streaming_bubble
        self._fade_in_widget(self._streaming_bubble, 200)
        row.addWidget(self._streaming_bubble)
        row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, container
        )

        # V17 Phase 2 : timer progressif
        self._stream_start_time = time.monotonic()
        self._time_label.setText("⏱  0.0s")
        self._time_label.setVisible(True)
        if self._progress_timer is None:
            self._progress_timer = QTimer(self)
            self._progress_timer.setInterval(100)  # ms — 10 FPS
            self._progress_timer.timeout.connect(self._update_progress_timer)
        self._progress_timer.start()

        QTimer.singleShot(50, self._scroll_to_bottom)

    def append_to_stream(self, chunk: str) -> None:
        """Ajoute un fragment de texte à la bulle de streaming.

        Utilise un buffer + timer pour grouper les tokens
        et éviter de repeindre trop souvent.

        Glue spaces : si le dernier fragment ne se termine pas par un
        espace et que le nouveau ne commence pas par un, on insère un
        espace. Compense un comportement de streaming où certains
        providers (openrouter deepseek notamment) envoient des tokens
        sans espaces entre eux (mots collés). Désactivable via
        ``self._glue_spaces = False``.
        """
        if not self._glue_spaces or not self._stream_buffer:
            self._stream_buffer.append(chunk)
        else:
            prev = self._stream_buffer[-1]
            # Si le buffer précédent ne finit pas par un séparateur
            # ET que le nouveau chunk ne commence pas par un séparateur
            # → ajouter un espace pour éviter les mots collés.
            sep_chars = " \n\t.,;:!?)]}-—"
            needs_space = (
                prev
                and not prev[-1].isspace()
                and not prev.endswith(tuple(sep_chars))
                and not prev[0].isspace()  # V17 FIX : si prev a déjà un espace en tête (MLX BPE), ne pas ajouter
                and chunk
                and not chunk[0].isspace()
                and not chunk.startswith(tuple(sep_chars))
            )
            if needs_space:
                self._stream_buffer.append(" " + chunk)
            else:
                self._stream_buffer.append(chunk)

        # Déclencher le flush immédiatement (timer unique)
        if self._stream_timer is None or not self._stream_timer.isActive():
            # V16 AUDIT FIX QW9 : parent QTimer(self) — évite fuite si widget détruit
            self._stream_timer = QTimer(self)
            self._stream_timer.setSingleShot(True)
            self._stream_timer.timeout.connect(self._flush_stream_buffer)
            self._stream_timer.start(30)  # ms — batch tokens toutes les 30ms

    def _flush_stream_buffer(self) -> None:
        """Vide le buffer dans la bulle de streaming."""
        if not self._stream_buffer or self._streaming_bubble is None:
            return

        text = "".join(self._stream_buffer)
        self._stream_buffer = []

        # Échapper le HTML avant insertion
        safe = (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>"))
        self._streaming_bubble.append_html(safe)
        self._scroll_to_bottom()

    def end_stream(self) -> None:
        """Finalise la bulle de streaming."""
        # Vider le buffer restant
        self._flush_stream_buffer()
        self._streaming_bubble = None

        # Nettoyer le timer stream
        if self._stream_timer and self._stream_timer.isActive():
            self._stream_timer.stop()
        self._stream_timer = None

        # V17 Phase 2 : arrêter le timer progressif
        if self._progress_timer and self._progress_timer.isActive():
            self._progress_timer.stop()
        elapsed = time.monotonic() - self._stream_start_time
        self._time_label.setText(f"✅  {elapsed:.1f}s")
        # Cacher après 2s
        QTimer.singleShot(2000, lambda: self._time_label.setVisible(False))

    # ── Utilitaires ──

    def _update_progress_timer(self) -> None:
        """Met à jour l'affichage du timer ⏱ pendant le streaming."""
        if self._stream_start_time <= 0:
            return
        elapsed = time.monotonic() - self._stream_start_time
        self._time_label.setText(f"⏱  {elapsed:.1f}s")

    def _scroll_to_bottom(self):
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self):
        self.end_stream()
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._last_assistant_bubble = None

    def set_metadata(self, metadata: dict) -> None:
        """Affiche le bandeau de confiance sur la dernière bulle assistant."""
        if self._last_assistant_bubble:
            self._last_assistant_bubble.set_metadata(metadata)

    # ── Indicateur de stratégie pipeline ──

    STRATEGY_LABELS = {
        "routing": "🔍  Analyse du contexte…",
        "rag": "📚  Recherche documents…",
        "generation": "⚡  Génération…",
        "completed": "✅  Terminé",
        "thinking": "💭  Réflexion…",
    }

    def set_strategy(self, key: str) -> None:
        """Affiche l'étape courante du pipeline dans la zone de chat."""
        label = self.STRATEGY_LABELS.get(key, f"⏳ {key}…")
        self._strategy_label.setText(label)
        self._strategy_label.setVisible(True)

    def hide_strategy(self) -> None:
        """Cache l'indicateur de stratégie."""
        self._strategy_label.setVisible(False)

    def _fade_in_widget(self, widget: QWidget, duration: int = 200) -> None:
        """Ajoute un effet de fade-in subtil sur un widget (bulle, etc.)."""
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        # Référence pour éviter le GC
        widget._fade_anim = anim
