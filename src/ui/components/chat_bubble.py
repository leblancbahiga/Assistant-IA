"""
NURU — ChatBubble : design Aether Dashboard.

- Avatar circulaire (36px) lettre "N" dégradé bleu-violet (#00d4ff → #a855f7)
- Bulle violet sombre #16162a, bordure 1px rgba(168,85,247,0.2)
- Barre de confiance RAG horizontale avec gradient vert
- Actions 👍 👎 📋 en boutons carrés arrondis
- Tags fichier : pastille verte #064e3b, texte #22c55e
- Curseur streaming cyan clignotant ▊
- Badge utilisateur "LB" avatar small à droite
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSizePolicy, QFrame, QProgressBar
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, Property, QEasingCurve
from PySide6.QtGui import QTextCursor, QPainter, QLinearGradient, QColor, QBrush, QFont
import datetime


# ── Avatar avec dégradé (peint "N") ──

class GradientAvatar(QLabel):
    """Avatar circulaire 36px avec lettre 'N' et fond dégradé bleu-violet."""

    def __init__(self, letter: str = "N", size: int = 36, parent=None):
        super().__init__(parent)
        self._letter = letter
        self._size = size
        self._pulse = 0.0  # 0.0 = normal, 1.0 = max pulse
        self._pulse_anim = QPropertyAnimation(self, b"pulse")
        self._pulse_anim.setDuration(800)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)

        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(size, size)
        self.setMaximumSize(size, size)

    def get_pulse(self) -> float:
        return self._pulse

    def set_pulse(self, val: float):
        self._pulse = val
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def start_pulse(self):
        """Animer l'avatar avec un pulse lumineux (streaming)."""
        if not self._pulse_anim.state() == QPropertyAnimation.State.Running:
            self._pulse_anim.start()

    def stop_pulse(self):
        """Arrêter l'animation pulse."""
        self._pulse_anim.stop()
        self._pulse = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Taille réelle
        w = self.width()
        h = self.height()
        r = min(w, h) // 2

        # Dégradé bleu → violet
        gradient = QLinearGradient(0, 0, w, h)
        gradient.setColorAt(0.0, QColor("#00d4ff"))
        gradient.setColorAt(1.0, QColor("#a855f7"))

        # Pulse : intensifier la luminosité pendant streaming
        pulse_intensity = self._pulse * 60  # max +60 sur chaque canal
        base_color = QColor("#00d4ff")
        pulse_color = QColor(
            min(255, base_color.red() + int(pulse_intensity * 0.6)),
            min(255, base_color.green() + int(pulse_intensity * 0.4)),
            min(255, base_color.blue() + int(pulse_intensity)),
        )

        if self._pulse > 0.01:
            # Pendant le pulse, on ajoute un halo externe
            glow_size = int(self._pulse * 4)
            glow_gradient = QLinearGradient(0, 0, w, h)
            glow_gradient.setColorAt(0.0, pulse_color)
            glow_gradient.setColorAt(1.0, QColor("#a855f7"))
            painter.setBrush(QBrush(glow_gradient))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(-glow_size, -glow_size, w + glow_size * 2, h + glow_size * 2, r + glow_size, r + glow_size)

        # Cercle de fond avec dégradé
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, r, r)

        # Texte "N" en blanc
        painter.setPen(QColor("#ffffff"))
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._letter)

        painter.end()


class UserAvatarBadge(QLabel):
    """Petit badge avatar utilisateur — initiales sur fond gris."""

    def __init__(self, initials: str = "LB", size: int = 28, parent=None):
        super().__init__(initials, parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "background-color: #1e293b;"
            "border: 1px solid rgba(0, 212, 255, 0.4);"
            f"border-radius: {size // 2}px;"
            "color: #00d4ff;"
            "font-size: 11px;"
            "font-weight: bold;"
        )


# ── Indicateur de frappe ──

class TypingIndicator(QLabel):
    """Indicateur de frappe clignotant — curseur ▊ cyan."""

    def __init__(self, parent=None):
        super().__init__("▊", parent)
        self.setStyleSheet("color: #00d4ff; font-size: 18px; font-weight: bold;")
        self._visible = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._blink)
        self._timer.start(500)

    def _blink(self):
        self._visible = not self._visible
        self.setText("▊" if self._visible else " ")

    def stop(self):
        self._timer.stop()
        self.setText("")


# ── Barre de confiance RAG ──

class RagConfidenceBar(QWidget):
    """Barre de confiance horizontale avec gradient de couleur et score numérique."""

    def __init__(self, score: float = 0.0, parent=None):
        super().__init__(parent)
        self._score = max(0.0, min(1.0, score))
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Barre de progression personnalisée
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(int(self._score * 100))
        self.progress.setFixedHeight(6)
        self.progress.setFixedWidth(80)
        self.progress.setTextVisible(False)
        self.progress.setObjectName("RagConfidenceBar")

        # Style adapté au score
        self._apply_bar_style()

        layout.addWidget(self.progress)

        # Label score
        self.score_label = QLabel(f"{(self._score * 100):.0f}%")
        self.score_label.setStyleSheet(
            "color: #22c55e; font-size: 9px; font-weight: bold;"
        )
        layout.addWidget(self.score_label)

        layout.addStretch()

    def _apply_bar_style(self):
        """Applique le style gradient selon le score."""
        if self._score >= 0.75:
            chunk = "#22c55e"
            bg = "rgba(34, 197, 94, 0.15)"
        elif self._score >= 0.40:
            chunk = "#f59e0b"
            bg = "rgba(245, 158, 11, 0.15)"
        else:
            chunk = "#ef4444"
            bg = "rgba(239, 68, 68, 0.15)"

        self.progress.setStyleSheet(f"""
            #RagConfidenceBar {{
                background-color: {bg};
                border: none;
                border-radius: 3px;
            }}
            #RagConfidenceBar::chunk {{
                background-color: {chunk};
                border-radius: 3px;
            }}
        """)

    def set_score(self, score: float):
        self._score = max(0.0, min(1.0, score))
        self.progress.setValue(int(self._score * 100))
        self.score_label.setText(f"{(self._score * 100):.0f}%")
        self._apply_bar_style()


# ── Tag fichier ──

class FileTag(QLabel):
    """Pastille verte indiquant une source fichier."""

    def __init__(self, filename: str = "", parent=None):
        display = f"📄 {filename}" if filename else "📄 Fichier"
        super().__init__(display, parent)
        self.setStyleSheet(
            "background-color: #064e3b;"
            "color: #22c55e;"
            "font-size: 9px;"
            "font-weight: bold;"
            "border-radius: 4px;"
            "padding: 2px 8px;"
        )


# ── Bouton d'action carré ──

class ActionButton(QPushButton):
    """Bouton d'action carré arrondi pour les feedbacks."""

    def __init__(self, text: str, tooltip: str = "", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(32, 32)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.04);
                color: #6B7280;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(168, 85, 247, 0.15);
                color: #a855f7;
                border: 1px solid rgba(168, 85, 247, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(168, 85, 247, 0.25);
            }
        """)

    def set_active(self, active: bool = True):
        """Highlight le bouton quand activé (vote déjà donné)."""
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(168, 85, 247, 0.2);
                    color: #a855f7;
                    border: 1px solid rgba(168, 85, 247, 0.4);
                    border-radius: 6px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(168, 85, 247, 0.3);
                }
            """)


# ── ChatBubble principale ──

class ChatBubble(QWidget):
    """Bulle de discussion — design Aether Dashboard.

    - Avatar IA dégradé bleu-violet avec lettre "N"
    - Bulle violet sombre #16162a avec bordure subtile
    - Barre de confiance RAG horizontale
    - Actions 👍 👎 📋 en boutons carrés arrondis
    - Tags fichier (pastille verte)
    - Curseur streaming cyan clignotant ▊
    - Pulse animation sur l'avatar pendant la génération
    - Avatar utilisateur "LB" à droite
    """

    feedback_given = Signal(str, str)  # (vote: 'up'|'down', message)

    def __init__(self, sender: str, message: str, is_user: bool = False, rag_score: float = None,
                 file_tags: list[str] = None, parent=None):
        super().__init__(parent)

        self._rag_score = rag_score
        self._is_user = is_user
        self._file_tags = file_tags or []
        self._feedback_state: str = ""  # "up", "down", ou ""

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setSpacing(8)

        # ── Avatar IA (gauche) ──
        self.avatar = GradientAvatar("N", 36)
        self.avatar.setVisible(not is_user)
        main_layout.addWidget(self.avatar, 0, Qt.AlignTop)

        # ── Bulle ──
        if is_user:
            bg_color = "#1a1a2e"
            border_color = "rgba(0, 212, 255, 0.3)"
            text_color = "#e2e8f0"
        else:
            bg_color = "#16162a"
            border_color = "rgba(168, 85, 247, 0.2)"
            text_color = "#e2e8f0"

        self.bubble = QFrame()
        self.bubble.setObjectName("AetherBubble")
        self.bubble.setStyleSheet(f"""
            #AetherBubble {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
                padding: 12px;
            }}
        """)

        content_layout = QVBoxLayout(self.bubble)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(6)

        # ── En-tête ──
        header = QHBoxLayout()
        header.setSpacing(8)

        if not is_user:
            # Badge "NURU"
            badge = QLabel("⚡ NURU")
            badge.setStyleSheet(
                "background-color: rgba(168, 85, 247, 0.15);"
                "color: #a855f7; font-size: 8px; font-weight: bold;"
                "border-radius: 4px; padding: 1px 6px;"
            )
            header.addWidget(badge)
        else:
            # Badge "VOUS"
            badge = QLabel("VOUS")
            badge.setStyleSheet(
                "background-color: rgba(0, 212, 255, 0.12);"
                "color: #00d4ff; font-size: 8px; font-weight: bold;"
                "border-radius: 4px; padding: 1px 6px;"
            )
            header.addWidget(badge)

        header.addStretch()

        # Timestamp
        time_lbl = QLabel(datetime.datetime.now().strftime("%H:%M"))
        time_lbl.setStyleSheet("color: #6B7280; font-size: 9px;")
        header.addWidget(time_lbl)

        content_layout.addLayout(header)

        # ── Tags fichier (assistant seulement, en haut du message) ──
        if not is_user and self._file_tags:
            tags_layout = QHBoxLayout()
            tags_layout.setSpacing(4)
            for tag in self._file_tags:
                ft = FileTag(tag)
                tags_layout.addWidget(ft)
            tags_layout.addStretch()
            content_layout.addLayout(tags_layout)

        # ── Message ──
        self.msg_text = QTextEdit()
        self.msg_text.setReadOnly(True)
        self.msg_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.msg_text.setFrameShape(QFrame.NoFrame)
        self.msg_text.setStyleSheet(
            f"background: transparent; color: {text_color}; font-size: 13px;"
        )
        self.msg_text.setPlainText(message)
        self.msg_text.document().setDocumentMargin(0)
        self.msg_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.msg_text.textChanged.connect(self._resize_to_content)
        content_layout.addWidget(self.msg_text)

        # ── Indicateur de frappe (caché par défaut) ──
        self.typing = TypingIndicator()
        self.typing.setVisible(False)
        content_layout.addWidget(self.typing)

        # ── Barre de confiance RAG (assistant seulement) ──
        if not is_user:
            self._rag_bar = RagConfidenceBar(rag_score or 0.0)
            self._rag_bar.setVisible(rag_score is not None)
            content_layout.addWidget(self._rag_bar)

        # ── Actions (assistant seulement) ──
        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 4, 0, 0)
            actions_layout.setSpacing(6)

            self.btn_up = ActionButton("👍", "Utile")
            self.btn_down = ActionButton("👎", "Pas utile")
            self.btn_copy = ActionButton("📋", "Copier le message")

            self.btn_up.clicked.connect(lambda: self._emit_feedback("up"))
            self.btn_down.clicked.connect(lambda: self._emit_feedback("down"))
            self.btn_copy.clicked.connect(self._copy_message)

            actions_layout.addWidget(self.btn_up)
            actions_layout.addWidget(self.btn_down)
            actions_layout.addWidget(self.btn_copy)
            actions_layout.addStretch()

            content_layout.addLayout(actions_layout)

        main_layout.addWidget(self.bubble, 1)

        # ── Avatar utilisateur (droite) ──
        if is_user:
            self.user_avatar = UserAvatarBadge("LB", 28)
            main_layout.addWidget(self.user_avatar, 0, Qt.AlignTop)
            # Pousse la bulle à droite
            main_layout.insertStretch(0, 1)
        else:
            main_layout.addStretch(1)

    def _emit_feedback(self, vote: str):
        """Émet le signal de feedback et highlight le bouton."""
        if self._feedback_state == vote:
            return  # déjà voté
        self._feedback_state = vote
        self.btn_up.set_active(vote == "up")
        self.btn_down.set_active(vote == "down")
        self.feedback_given.emit(vote, self.msg_text.toPlainText())

    def _copy_message(self):
        """Copie le message dans le presse-papier."""
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.msg_text.toPlainText())
        # Feedback visuel temporaire
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: rgba(34, 197, 94, 0.15);
                color: #22c55e;
                border: 1px solid rgba(34, 197, 94, 0.3);
                border-radius: 6px;
                font-size: 14px;
            }
        """)
        QTimer.singleShot(1500, lambda: self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.04);
                color: #6B7280;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(168, 85, 247, 0.15);
                color: #a855f7;
                border: 1px solid rgba(168, 85, 247, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(168, 85, 247, 0.25);
            }
        """))

    # ── API publique (inchangée pour compatibilité console_page) ──

    def set_rag_score(self, score: float):
        """Met à jour la barre de confiance RAG."""
        self._rag_score = score
        if hasattr(self, '_rag_bar'):
            self._rag_bar.set_score(score)
            self._rag_bar.setVisible(True)

    def append_text(self, text: str):
        """Ajoute du texte au message existant (streaming)."""
        try:
            cursor = self.msg_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.msg_text.setTextCursor(cursor)
            self._resize_to_content()
        except RuntimeError:
            pass

    def show_typing(self):
        """Affiche l'indicateur de frappe clignotant et active le pulse avatar."""
        self.typing.setVisible(True)
        if hasattr(self, 'avatar'):
            self.avatar.start_pulse()

    def hide_typing(self):
        """Cache l'indicateur de frappe et arrête le pulse."""
        self.typing.stop()
        self.typing.setVisible(False)
        if hasattr(self, 'avatar'):
            self.avatar.stop_pulse()

    def finalize_response(self):
        """Post-traitement : arrête le curseur clignotant et le pulse."""
        self.hide_typing()

    def set_file_tags(self, tags: list[str]):
        """Ajoute des tags fichier après coup (streaming)."""
        self._file_tags = tags or []
        # Mise à jour simple — efface et recrée si nécessaire
        from PySide6.QtWidgets import QLayout
        content_layout = self.bubble.layout()
        if content_layout:
            # Chercher et supprimer l'ancien layout de tags (item 1 après l'en-tête)
            for i in range(content_layout.count()):
                item = content_layout.itemAt(i)
                if item and item.layout() and isinstance(item.layout(), QHBoxLayout):
                    # Vérifier si c'est notre layout de tags
                    for j in range(item.layout().count()):
                        w = item.layout().itemAt(j)
                        if w and w.widget() and isinstance(w.widget(), FileTag):
                            # Supprimer l'ancien layout de tags
                            self._clear_layout_item(content_layout, i)
                            break
                    else:
                        continue
                    break

            # Ajouter les nouveaux tags
            if self._file_tags and not self._is_user:
                tags_layout = QHBoxLayout()
                tags_layout.setSpacing(4)
                for tag in self._file_tags:
                    ft = FileTag(tag)
                    tags_layout.addWidget(ft)
                tags_layout.addStretch()
                # Insérer après l'en-tête (index 0)
                content_layout.insertLayout(1, tags_layout)

    @staticmethod
    def _clear_layout_item(layout, index):
        """Supprime un item de layout proprement."""
        item = layout.takeAt(index)
        if item:
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child and child.widget():
                        child.widget().deleteLater()
            elif item.widget():
                item.widget().deleteLater()

    def _resize_to_content(self):
        try:
            doc = self.msg_text.document()
            doc.setTextWidth(self.msg_text.viewport().width())
            h = doc.documentLayout().documentSize().height()
            if h > 0:
                self.msg_text.setFixedHeight(int(h) + 4)
        except Exception:
            pass
