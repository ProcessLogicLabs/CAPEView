"""CAPEView Animated Splash Screen.

Adapted from TariffMill's animated_splash.py (open-tariffmill). Re-skinned to
the muted-cyan palette defined in theme.SPLASH_COLORS.

Public API matches TariffMill so usage stays familiar:
    splash = AnimatedMillSplash("CAPEView", "0.0.1")
    splash.show(); splash.setText("..."); splash.setProgress(50); splash.fadeOut()
"""

import math
import time

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt5.QtWidgets import QApplication, QWidget

from CAPEView.theme import SPLASH_COLORS as C


class AnimatedMillSplash(QWidget):
    """Premium splash screen for CAPEView."""

    def __init__(self, app_name: str = "CAPEView", version: str = "", parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.version = version

        self.start_time = time.time()
        self.fade_opacity = 1.0
        self.is_fading = False

        self._progress = 0
        self._target_progress = 0
        self._message = "Initializing..."

        self.intro_progress = 0.0
        self.ring_rotation = 0.0
        self.pulse_phase = 0.0
        self.wave_offset = 0.0

        self.setFixedSize(540, 340)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(16)

    def _animate(self):
        elapsed = time.time() - self.start_time

        if self.is_fading:
            self.fade_opacity = max(0, self.fade_opacity - 0.04)
            if self.fade_opacity <= 0:
                self.timer.stop()
                self.close()
                return

        if elapsed < 1.0:
            self.intro_progress = self._ease_out_expo(elapsed / 1.0)
        else:
            self.intro_progress = 1.0

        self.ring_rotation = elapsed * 30
        self.pulse_phase = elapsed * 2.5
        self.wave_offset = elapsed * 80

        diff = self._target_progress - self._progress
        self._progress += diff * 0.1

        self.update()

    def _ease_out_expo(self, t: float) -> float:
        return 1 if t == 1 else 1 - pow(2, -10 * t)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)

        painter.fillRect(self.rect(), QColor(*C["bg_top"]))

        self._draw_background(painter)
        self._draw_orbital_rings(painter)
        self._draw_center_emblem(painter)
        self._draw_title(painter)
        self._draw_tagline(painter)
        self._draw_progress_area(painter)
        self._draw_corner_accents(painter)
        self._draw_version(painter)

        painter.end()

    def _draw_background(self, painter):
        painter.save()
        bg = QLinearGradient(0, 0, self.width(), self.height())
        bg.setColorAt(0, QColor(*C["bg_top"]))
        bg.setColorAt(0.5, QColor(*C["bg_mid"]))
        bg.setColorAt(1, QColor(*C["bg_bottom"]))
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        glow_rect = QRectF(0, 0, self.width(), 140)
        glow = QLinearGradient(0, 0, 0, 140)
        glow.setColorAt(0, QColor(*C["ring_a"][:3], 25))
        glow.setColorAt(1, QColor(*C["ring_a"][:3], 0))
        painter.setBrush(glow)
        painter.drawRect(glow_rect)

        painter.setBrush(Qt.NoBrush)
        border_pen = QPen(QColor(*C["border"]))
        border_pen.setWidth(2)
        painter.setPen(border_pen)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        painter.restore()

    def _draw_orbital_rings(self, painter):
        painter.save()
        cx, cy = self.width() / 2, 100
        opacity = self.intro_progress * 0.7

        painter.translate(cx, cy)
        painter.rotate(self.ring_rotation)

        pen = QPen(QColor(*C["ring_a"][:3], int(C["ring_a"][3] * opacity)))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(-50, -50, 100, 100), 0, 120 * 16)

        pen.setColor(QColor(*C["ring_b"][:3], int(C["ring_b"][3] * opacity)))
        painter.setPen(pen)
        painter.drawArc(QRectF(-50, -50, 100, 100), 180 * 16, 120 * 16)

        painter.rotate(-self.ring_rotation * 2)

        pen.setColor(QColor(*C["ring_c"][:3], int(C["ring_c"][3] * opacity)))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawArc(QRectF(-36, -36, 72, 72), 60 * 16, 120 * 16)

        pen.setColor(QColor(*C["ring_a"][:3], int(C["ring_a"][3] * opacity * 0.75)))
        painter.setPen(pen)
        painter.drawArc(QRectF(-36, -36, 72, 72), 240 * 16, 120 * 16)
        painter.restore()

    def _draw_center_emblem(self, painter):
        painter.save()
        cx, cy = self.width() / 2, 100
        scale = self.intro_progress

        painter.translate(cx, cy)
        painter.scale(scale, scale)

        glow = QRadialGradient(0, 0, 45)
        glow.setColorAt(0, QColor(*C["ring_a"][:3], 70))
        glow.setColorAt(0.6, QColor(*C["ring_b"][:3], 40))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), 45, 45)

        emblem_bg = QRadialGradient(0, -8, 32)
        emblem_bg.setColorAt(0, QColor(*C["emblem_bg_inner"]))
        emblem_bg.setColorAt(1, QColor(*C["emblem_bg_outer"]))
        painter.setBrush(emblem_bg)
        pen = QPen(QColor(*C["emblem_border"]))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(0, 0), 28, 28)

        pulse = 0.85 + 0.15 * math.sin(self.pulse_phase)
        pen = QPen(QColor(*C["emblem_pulse"][:3], C["emblem_pulse"][3]))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 20 * pulse, 20 * pulse)

        font = QFont("Segoe UI", 14, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0, 60))
        painter.drawText(QRectF(-20, -9, 40, 22), Qt.AlignCenter, "CV")
        painter.setPen(QColor(*C["emblem_text"]))
        painter.drawText(QRectF(-20, -10, 40, 22), Qt.AlignCenter, "CV")
        painter.restore()

    def _draw_title(self, painter):
        painter.save()
        opacity = max(0, (self.intro_progress - 0.2) / 0.8) if self.intro_progress > 0.2 else 0

        font = QFont("Segoe UI", 36, QFont.Light)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        painter.setFont(font)

        title_rect = QRectF(0, 155, self.width(), 50)
        painter.setPen(QColor(0, 0, 0, int(50 * opacity)))
        painter.drawText(title_rect.adjusted(2, 2, 2, 2), Qt.AlignCenter, self.app_name)
        painter.setPen(QColor(*C["title"], int(255 * opacity)))
        painter.drawText(title_rect, Qt.AlignCenter, self.app_name)
        painter.restore()

    def _draw_tagline(self, painter):
        painter.save()
        opacity = max(0, (self.intro_progress - 0.4) / 0.6) if self.intro_progress > 0.4 else 0

        font = QFont("Segoe UI", 10)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.setPen(QColor(*C["tagline"], int(255 * opacity)))
        painter.drawText(QRectF(0, 205, self.width(), 25), Qt.AlignCenter,
                         "CAPE ENTRY TRACKING & COMPLIANCE")
        painter.restore()

    def _draw_progress_area(self, painter):
        painter.save()
        opacity = max(0, (self.intro_progress - 0.5) / 0.5) if self.intro_progress > 0.5 else 0

        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.setPen(QColor(*C["tagline"], int(255 * opacity)))
        painter.drawText(QRectF(0, 248, self.width(), 20), Qt.AlignCenter, self._message)

        bar_width = 320
        bar_height = 5
        bar_x = (self.width() - bar_width) / 2
        bar_y = 278

        painter.setBrush(QColor(*C["progress_track"], int(255 * opacity)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_width, bar_height), 2, 2)

        if self._progress > 0.5:
            fill_width = (self._progress / 100) * bar_width
            offset = self.wave_offset % (bar_width * 2)
            fill_grad = QLinearGradient(bar_x - offset, 0, bar_x + bar_width * 2 - offset, 0)
            fill_grad.setColorAt(0, QColor(*C["progress_fill_a"]))
            fill_grad.setColorAt(0.33, QColor(*C["progress_fill_b"]))
            fill_grad.setColorAt(0.66, QColor(*C["progress_fill_c"]))
            fill_grad.setColorAt(1, QColor(*C["progress_fill_a"]))

            painter.setClipRect(QRectF(bar_x, bar_y, fill_width, bar_height))
            painter.setBrush(fill_grad)
            painter.setOpacity(opacity)
            painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_width, bar_height), 2, 2)
            painter.setClipping(False)

            shine = QLinearGradient(0, bar_y, 0, bar_y + bar_height)
            shine.setColorAt(0, QColor(255, 255, 255, 80))
            shine.setColorAt(0.5, QColor(255, 255, 255, 0))
            painter.setClipRect(QRectF(bar_x, bar_y, fill_width, bar_height / 2))
            painter.setBrush(shine)
            painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_width, bar_height), 2, 2)
            painter.setClipping(False)

        painter.setOpacity(opacity)
        pct_font = QFont("Segoe UI", 9)
        painter.setFont(pct_font)
        painter.setPen(QColor(*C["version"]))
        painter.drawText(QRectF(bar_x + bar_width + 12, bar_y - 3, 50, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, f"{int(self._progress)}%")
        painter.restore()

    def _draw_corner_accents(self, painter):
        painter.save()
        opacity = self.intro_progress * 0.30

        pen = QPen(QColor(*C["corner_accent"], int(255 * opacity)))
        pen.setWidth(2)
        painter.setPen(pen)
        # Top-left
        painter.drawLine(15, 12, 40, 12)
        painter.drawLine(12, 15, 12, 40)
        # Top-right
        painter.drawLine(self.width() - 40, 12, self.width() - 15, 12)
        painter.drawLine(self.width() - 12, 15, self.width() - 12, 40)
        # Bottom-left
        painter.drawLine(15, self.height() - 12, 40, self.height() - 12)
        painter.drawLine(12, self.height() - 40, 12, self.height() - 15)
        # Bottom-right
        painter.drawLine(self.width() - 40, self.height() - 12, self.width() - 15, self.height() - 12)
        painter.drawLine(self.width() - 12, self.height() - 40, self.width() - 12, self.height() - 15)
        painter.restore()

    def _draw_version(self, painter):
        if not self.version:
            return
        painter.save()
        opacity = max(0, (self.intro_progress - 0.6) / 0.4) if self.intro_progress > 0.6 else 0
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(QColor(*C["version"], int(180 * opacity)))
        painter.drawText(QRectF(0, 308, self.width(), 20), Qt.AlignCenter, f"v{self.version.lstrip('v')}")
        painter.restore()

    def setText(self, text: str):
        self._message = text

    def setProgress(self, value: int):
        self._target_progress = min(100, max(0, value))

    def setVersion(self, version: str):
        self.version = version

    def fadeOut(self):
        self.is_fading = True

    def stop(self):
        self.timer.stop()


def create_splash(app_name: str = "CAPEView", version: str = "") -> AnimatedMillSplash:
    return AnimatedMillSplash(app_name, version)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    splash = create_splash("CAPEView", "0.0.1")
    splash.show()

    screen_geo = app.desktop().availableGeometry()
    splash.move(
        (screen_geo.width() - splash.width()) // 2,
        (screen_geo.height() - splash.height()) // 2,
    )

    def update_progress():
        current = splash._target_progress
        if current < 100:
            splash.setProgress(current + 2)
            messages = [
                "Loading configuration...",
                "Connecting to database...",
                "Loading user preferences...",
                "Initializing workspace...",
                "Starting services...",
                "Almost ready...",
            ]
            msg_idx = min(current // 18, len(messages) - 1)
            splash.setText(messages[msg_idx])
        else:
            splash.fadeOut()

    progress_timer = QTimer()
    progress_timer.timeout.connect(update_progress)
    QTimer.singleShot(800, lambda: progress_timer.start(50))

    sys.exit(app.exec_())
