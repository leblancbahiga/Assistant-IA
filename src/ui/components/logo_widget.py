from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QRadialGradient, QBrush, QPixmap
from PySide6.QtCore import Qt, QTimer, QRectF, QPoint
from PySide6.QtSvg import QSvgRenderer
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AnimatedLogo(QWidget):
    """Logo NURU basé sur gemini-svg.svg avec halo pulsant cyberpunk.
    Le SVG est rendu une fois dans un QPixmap cache pour éviter de
    re-rendre le SVG à chaque frame (trop coûteux).
    """

    def __init__(self, size=60, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.angle_outer = 0
        self.angle_inner = 0
        self.pulse = 0
        self.pulse_dir = 1
        self._cached_svg = None  # QPixmap cache

        # Charger le SVG du logo et le pixelliser une fois
        self.renderer = None
        try:
            svg_path = Path(__file__).parent.parent / "assets" / "gemini-logo.svg"
            if svg_path.exists():
                self.renderer = QSvgRenderer(str(svg_path))
                if self.renderer.isValid():
                    logger.info(f"✅ Logo SVG chargé : {svg_path}")
                    # Pre-rendre le SVG dans un QPixmap cache
                    self._cached_svg = QPixmap(size, size)
                    self._cached_svg.fill(Qt.transparent)
                    img_painter = QPainter(self._cached_svg)
                    self.renderer.render(img_painter, QRectF(0, 0, size, size))
                    img_painter.end()
                else:
                    self.renderer = None
                    logger.warning(f"⚠ SVG invalide : {svg_path}")
            else:
                logger.warning(f"⚠ Logo SVG introuvable : {svg_path}")
        except Exception as e:
            logger.error(f"❌ Erreur chargement SVG : {e}")

        # Timer pour l'animation à 30 FPS (~33ms) — suffisant pour un halo
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(33)

    def update_animation(self):
        self.angle_outer = (self.angle_outer + 1) % 360
        self.angle_inner = (self.angle_inner - 2) % 360

        self.pulse += 0.025 * self.pulse_dir
        if self.pulse > 1.0:
            self.pulse_dir = -1
        elif self.pulse < 0.0:
            self.pulse_dir = 1

        self.update()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            center = QPoint(self.width() // 2, self.height() // 2)

            if self._cached_svg is not None:
                # ═══ AFFICHAGE CACHE SVG + EFFETS LÉGERS ═══
                s = self.width()

                # 1. Halo extérieur pulsant
                glow_radius = s / 2 - 1
                glow_gradient = QRadialGradient(center, glow_radius)
                glow_gradient.setColorAt(0, QColor(0, 242, 255, int(120 * self.pulse)))
                glow_gradient.setColorAt(0.6, QColor(139, 92, 246, int(60 * self.pulse)))
                glow_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))

                painter.setBrush(QBrush(glow_gradient))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(center, glow_radius, glow_radius)

                # 2. Dessiner le pixmap pré-rendu (rapide — pas de rendu SVG)
                painter.drawPixmap(0, 0, self._cached_svg)

                # 3. Bordure néon
                painter.save()
                border_pen = QPen(QColor(0, 242, 255, int(150 + 105 * self.pulse)))
                border_pen.setWidth(2)
                painter.setPen(border_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(1, 1, s - 2, s - 2), 20, 20)
                painter.restore()

                # 4. Contre-rotation magentée (légère)
                painter.save()
                painter.translate(center)
                painter.rotate(-self.angle_outer * 2)
                pen_magenta = QPen(QColor(255, 0, 255, int(40 + 30 * self.pulse)))
                pen_magenta.setWidth(1)
                pen_magenta.setStyle(Qt.DashLine)
                painter.setPen(pen_magenta)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(-s*0.35, -s*0.35, s*0.7, s*0.7))
                painter.restore()

            else:
                # ═══ CODE DE SECOURS : cercle cyan + texte ═══
                halo_radius = 18 + (6 * self.pulse)
                halo_gradient = QRadialGradient(center, halo_radius)
                halo_gradient.setColorAt(0, QColor(0, 242, 255, int(80 * self.pulse)))
                halo_gradient.setColorAt(1, QColor(0, 242, 255, 0))
                painter.setBrush(QBrush(halo_gradient))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(center, halo_radius, halo_radius)

                painter.translate(center)

                painter.rotate(self.angle_outer)
                pen_outer = QPen(QColor(0, 242, 255, 180))
                pen_outer.setWidth(2)
                pen_outer.setCapStyle(Qt.RoundCap)
                painter.setPen(pen_outer)
                painter.setBrush(Qt.NoBrush)
                painter.drawArc(QRectF(-16, -16, 32, 32), 0 * 16, 120 * 16)
                painter.drawArc(QRectF(-16, -16, 32, 32), 180 * 16, 120 * 16)

                painter.rotate(-self.angle_outer * 2.5)
                pen_inner = QPen(QColor(255, 0, 255, 150))
                pen_inner.setWidth(1)
                pen_inner.setStyle(Qt.DashLine)
                painter.setPen(pen_inner)
                painter.drawEllipse(QRectF(-11, -11, 22, 22))

                painter.resetTransform()
                painter.translate(center)
                painter.setBrush(QBrush(QColor(255, 255, 255, int(150 + 105 * self.pulse))))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(0, 0), 3, 3)

        except Exception as e:
            logger.warning(f"Logo paint bypass: {e}")
