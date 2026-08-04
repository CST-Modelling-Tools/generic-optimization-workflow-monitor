from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget


class SparklineWidget(QWidget):
    """Small native Qt line chart with subtle area fill and endpoint marker."""

    _TONE_COLORS = {
        "neutral": QColor("#6C8FB3"),
        "good": QColor("#45C486"),
        "warning": QColor("#E3BF55"),
        "bad": QColor("#F36A76"),
        "accent": QColor("#9B72E8"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[float, ...] = ()
        self._tone = "neutral"
        self.setMinimumSize(72, 34)
        self.setMaximumHeight(42)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def values(self) -> tuple[float, ...]:
        return self._values

    @property
    def tone(self) -> str:
        return self._tone

    def sizeHint(self) -> QSize:
        return QSize(96, 36)

    def set_values(
        self,
        values: Iterable[float],
        *,
        tone: str = "neutral",
    ) -> None:
        self._values = tuple(
            float(value)
            for value in values
            if math.isfinite(float(value))
        )
        self._tone = tone if tone in self._TONE_COLORS else "neutral"
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(
            3.0,
            3.0,
            max(4.0, self.width() - 6.0),
            max(4.0, self.height() - 7.0),
        )
        painter.setPen(QPen(QColor("#1E3146"), 1.0))
        painter.drawLine(
            QPointF(rect.left(), rect.bottom()),
            QPointF(rect.right(), rect.bottom()),
        )

        if len(self._values) < 2:
            painter.end()
            return

        value_min = min(self._values)
        value_max = max(self._values)
        if value_min == value_max:
            padding = max(abs(value_min) * 0.05, 1.0)
            value_min -= padding
            value_max += padding

        path = QPainterPath()
        plotted_points: list[QPointF] = []
        last_index = len(self._values) - 1
        for index, value in enumerate(self._values):
            x = rect.left() + index / last_index * rect.width()
            ratio = (value - value_min) / (value_max - value_min)
            y = rect.bottom() - ratio * rect.height()
            point = QPointF(x, y)
            plotted_points.append(point)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        color = self._TONE_COLORS[self._tone]
        fill_path = QPainterPath(path)
        fill_path.lineTo(plotted_points[-1].x(), rect.bottom())
        fill_path.lineTo(plotted_points[0].x(), rect.bottom())
        fill_path.closeSubpath()

        gradient = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
        top_color = QColor(color)
        top_color.setAlpha(70)
        bottom_color = QColor(color)
        bottom_color.setAlpha(0)
        gradient.setColorAt(0.0, top_color)
        gradient.setColorAt(1.0, bottom_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(fill_path)

        line_pen = QPen(color, 1.7)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(plotted_points[-1], 2.2, 2.2)
        painter.end()
