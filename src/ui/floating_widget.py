"""
NURU V12 — Floating Widget
Design System DM-1 "Deep Cyan"

Specs (extraites mockup board V12):
  - 220x160px, Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint
  - Frosted glass effect (QPainter blur approximation)
  - Bordure cyan 1px, coins arrondis 12px
  - Contenu: mini orb + "NURU" + conversation preview
"""

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QPoint, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QRadialGradient, QPainterPath, QCursor
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
)


class FloatingWidget(QWidget):
    """Widget flottant 220x160px, frameless, frosted glass."""

    message_requested = Signal(str)

    # Design tokens DM-1
    BG = QColor(10, 14, 23, 200)       # #0A0E17 @ 78% alpha
    BORDER = QColor(0, 212, 255, 50)    # #00D4FF @ 20%
    CYAN = QColor(0, 212, 255)           # #00D4FF
    TEXT = QColor(232, 236, 241)         # #E8ECF1
    TEXT_DIM = QColor(139, 149, 165)     # #8B95A5
    SURFACE = QColor(21, 27, 38, 180)    # #151B26 @ 70%

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(260, 180)
        self._drag_pos = None
        self._theme_colors = self._dark_colors()
        self._is_dark = True

        self._setup_ui()

    # ── Palettes ──

    @staticmethod
    def _dark_colors():
        return {
            "bg": QColor(10, 14, 23, 200),
            "border": QColor(0, 212, 255, 50),
            "cyan": QColor(0, 212, 255),
            "text": QColor(232, 236, 241),
            "text_dim": QColor(139, 149, 165),
            "surface": QColor(21, 27, 38, 180),
        }

    @staticmethod
    def _light_colors():
        return {
            "bg": QColor(240, 244, 248, 200),
            "border": QColor(0, 153, 187, 40),
            "cyan": QColor(0, 153, 187),
            "text": QColor(26, 35, 50),
            "text_dim": QColor(107, 122, 144),
            "surface": QColor(255, 255, 255, 200),
        }

    def apply_theme(self, theme: str):
        """Met à jour les couleurs QPainter selon le thème."""
        self._is_dark = theme == "dark"
        self._theme_colors = self._dark_colors() if theme == "dark" else self._light_colors()
        # Mettre à jour les styles QSS des QLabel
        title_color = self._theme_colors["text"].name()
        dim_color = self._theme_colors["text_dim"].name()
        self._title.setStyleSheet(f"color: {title_color}; border: none; background: transparent;")
        self._subtitle.setStyleSheet(f"color: {dim_color}; border: none; background: transparent;")
        self._preview.setStyleSheet(
            f"color: {dim_color}; border: none; background: transparent; padding: 4px 0;"
        )
        sep_color = self._theme_colors["border"].name()
        self._sep.setStyleSheet(f"background: {sep_color}; border: none;")
        self.update()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        C = self._theme_colors
        text_name = C["text"].name()
        dim_name = C["text_dim"].name()
        border_name = C["border"].name()

        # Top row: mini orb + title
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._mini_orb = MiniOrb(self)
        self._mini_orb.setFixedSize(28, 28)
        top_row.addWidget(self._mini_orb)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        self._title = QLabel("NURU")
        self._title.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color: {text_name}; border: none; background: transparent;")
        title_layout.addWidget(self._title)

        self._subtitle = QLabel("Assistant prêt")
        self._subtitle.setFont(QFont("Inter", 10))
        self._subtitle.setStyleSheet(f"color: {dim_name}; border: none; background: transparent;")
        title_layout.addWidget(self._subtitle)

        top_row.addLayout(title_layout)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Separator
        self._sep = QWidget(self)
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(f"background: {border_name}; border: none;")
        layout.addWidget(self._sep)

        # Conversation preview
        self._preview = QLabel("Cliquez pour parler à NURU...")
        self._preview.setFont(QFont("Inter", 10, QFont.Weight.Light))
        self._preview.setStyleSheet(
            f"color: {dim_name}; border: none; background: transparent; padding: 4px 0;"
        )
        self._preview.setWordWrap(True)
        layout.addWidget(self._preview)

        layout.addStretch()

    def setStatus(self, text: str, color=None):
        self._subtitle.setText(text)
        if color:
            self._subtitle.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        else:
            dim = self._theme_colors["text_dim"].name()
            self._subtitle.setStyleSheet(f"color: {dim}; border: none; background: transparent;")

    def setPreview(self, text: str):
        self._preview.setText(text)
        text_color = self._theme_colors["text"].name()
        self._preview.setStyleSheet(
            f"color: {text_color}; border: none; background: transparent; padding: 4px 0;"
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        C = self._theme_colors

        # Frosted glass background
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)

        # Fill with semi-transparent
        painter.setPen(Qt.NoPen)
        painter.setBrush(C["bg"])
        painter.drawPath(path)

        # Frosted glass overlay (lighter center)
        glass = QRadialGradient(
            self.width() / 2, self.height() / 2, self.width() * 0.6
        )
        if self._is_dark:
            glass.setColorAt(0.0, QColor(30, 40, 55, 40))
        else:
            glass.setColorAt(0.0, QColor(255, 255, 255, 50))
        glass.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glass))
        painter.drawPath(path)

        # Cyan border 1px
        pen = QPen(C["border"], 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Top-edge glow line (subtle accent highlight)
        glow_color = QColor(C["cyan"])
        glow_color.setAlpha(30)
        painter.setPen(QPen(glow_color, 1))
        painter.drawLine(12, 1, self.width() - 12, 1)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.message_requested.emit("widget_click")

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ── Alias DM-1 : NuruFloatingWidget = FloatingWidget ──
NuruFloatingWidget = FloatingWidget


class MiniOrb(QWidget):
    """Mini version de l'orb pour le floating widget (28x28)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(60)

    def _animate(self):
        self._pulse += 0.05
        if self._pulse > 6.28:
            self._pulse -= 6.28
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        cx, cy = 14, 14
        r = 10 + 1.5 * (1 + self._pulse)

        # Glow
        glow = QRadialGradient(cx, cy, r + 4)
        glow.setColorAt(0.0, QColor(0, 212, 255, 40))
        glow.setColorAt(1.0, QColor(0, 212, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), r + 4, r + 4)

        # Orb
        gradient = QRadialGradient(cx - 2, cy - 2, r)
        gradient.setColorAt(0.0, QColor(200, 240, 255, 255))
        gradient.setColorAt(0.4, QColor(0, 212, 255, 255))
        gradient.setColorAt(1.0, QColor(0, 120, 160, 150))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.end()