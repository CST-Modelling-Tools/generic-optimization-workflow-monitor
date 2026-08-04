from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget


class SemicircleGauge(QWidget):
    """Compact half-dial gauge for bounded percentage metrics."""

    _TONE_COLORS = {
        "neutral": QColor("#6C8FB3"),
        "good": QColor("#45C486"),
        "warning": QColor("#E3BF55"),
        "bad": QColor("#F36A76"),
        "accent": QColor("#9B72E8"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value: float | None = None
        self._tone = "neutral"
        self.setMinimumSize(84, 44)
        self.setMaximumHeight(50)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def tone(self) -> str:
        return self._tone

    def sizeHint(self) -> QSize:
        return QSize(96, 48)

    def set_value(
        self,
        value: float | None,
        *,
        tone: str = "neutral",
    ) -> None:
        if value is None or not math.isfinite(float(value)):
            self._value = None
        else:
            self._value = min(100.0, max(0.0, float(value)))
        self._tone = tone if tone in self._TONE_COLORS else "neutral"
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = float(self.width())
        height = float(self.height())
        arc_rect = QRectF(8.0, 7.0, max(12.0, width - 16.0), max(12.0, height * 1.45))

        background_pen = QPen(QColor("#1E3146"), 6.0)
        background_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(background_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(arc_rect, 180 * 16, -180 * 16)

        if self._value is None:
            painter.end()
            return

        ratio = self._value / 100.0
        color = self._TONE_COLORS[self._tone]
        progress_pen = QPen(color, 6.0)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(
            arc_rect,
            180 * 16,
            round(-180 * ratio * 16),
        )

        center = QPointF(arc_rect.center().x(), arc_rect.center().y())
        radius = arc_rect.width() * 0.38
        angle = math.pi * (1.0 - ratio)
        needle_end = QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() - math.sin(angle) * radius,
        )

        needle_pen = QPen(QColor("#DCE6F2"), 1.5)
        needle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(needle_pen)
        painter.drawLine(center, needle_end)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#DCE6F2"))
        painter.drawEllipse(center, 2.6, 2.6)

        painter.end()
