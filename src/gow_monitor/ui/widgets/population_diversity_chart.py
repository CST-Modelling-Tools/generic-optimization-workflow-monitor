from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from gow_monitor.domain import EvaluationPoint
from gow_monitor.ui.dashboard_metrics import (
    PopulationDiversityPoint,
    population_diversity_series,
)
from gow_monitor.ui.formatting import format_fixed


class PopulationDiversityChart(QWidget):
    """Native dual-series diversity chart inspired by GOW diagnostics."""

    _SPREAD_COLOR = QColor("#4D8DFF")
    _ELLIPSE_COLOR = QColor("#FF9F43")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: tuple[EvaluationPoint, ...] = ()
        self._precomputed: tuple[PopulationDiversityPoint, ...] = ()
        self._window_size: int | None = None
        self.setMinimumHeight(125)
        self.setToolTip(
            "spread: sum of marginal sample standard deviations in normalized "
            "parameter space. ellipse_area: area of the 95% confidence ellipse "
            "in the two dominant PCA directions."
        )

    def sizeHint(self) -> QSize:
        return QSize(760, 145)

    @property
    def history(self) -> tuple[EvaluationPoint, ...]:
        return self._history

    @property
    def window_size(self) -> int | None:
        return self._window_size

    @property
    def series(self) -> tuple[PopulationDiversityPoint, ...]:
        return self.visible_samples()

    def set_history(self, history: Iterable[EvaluationPoint]) -> None:
        self._history = tuple(history)
        self.update()

    def set_precomputed_series(
        self,
        series: Iterable[PopulationDiversityPoint],
    ) -> None:
        self._precomputed = tuple(series)
        self.update()

    def set_window_size(self, window_size: int | None) -> None:
        if window_size is not None and window_size < 2:
            raise ValueError("window_size must be at least 2")
        self._window_size = window_size
        self.update()

    def visible_samples(self) -> tuple[PopulationDiversityPoint, ...]:
        samples = (
            self._precomputed
            if self._precomputed
            else population_diversity_series(self._history)
        )
        if self._window_size is None or not self._history:
            return samples

        visible_history = self._history[-self._window_size :]
        first_evaluation = visible_history[0].evaluation
        return tuple(
            sample
            for sample in samples
            if sample.evaluation >= first_evaluation
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0A121E"))

        chart_rect = QRectF(
            62.0,
            28.0,
            max(10.0, self.width() - 82.0),
            max(10.0, self.height() - 64.0),
        )
        painter.setPen(QPen(QColor("#22364B"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(chart_rect, 4.0, 4.0)

        samples = self.visible_samples()
        if not samples:
            painter.setPen(QColor("#7890A9"))
            painter.drawText(
                chart_rect,
                Qt.AlignmentFlag.AlignCenter,
                "No population parameter vectors available",
            )
            painter.end()
            return

        first_generation = samples[0].generation_id
        last_generation = samples[-1].generation_id
        mapped_last_generation = (
            last_generation + 1
            if first_generation == last_generation
            else last_generation
        )
        maximum = max(
            max(sample.spread, sample.ellipse_area)
            for sample in samples
        )
        y_max = max(0.1000, maximum * 1.1200)

        self._draw_axes(
            painter,
            chart_rect,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
            y_max=y_max,
        )
        spread_points = self._map_series(
            samples,
            "spread",
            chart_rect,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
            y_max=y_max,
        )
        ellipse_points = self._map_series(
            samples,
            "ellipse_area",
            chart_rect,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
            y_max=y_max,
        )
        self._draw_current_generation_marker(
            painter,
            chart_rect,
            generation=last_generation,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
        )
        self._draw_line(painter, spread_points, self._SPREAD_COLOR)
        self._draw_line(painter, ellipse_points, self._ELLIPSE_COLOR)
        self._draw_legend(painter, chart_rect)

        latest = samples[-1]
        painter.setPen(QColor("#91A4B9"))
        painter.drawText(
            QRectF(chart_rect.left(), 3.0, chart_rect.width() - 210.0, 19.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            (
                f"latest spread {format_fixed(latest.spread)}"
                f" | ellipse area {format_fixed(latest.ellipse_area)}"
                f" | population {latest.population_size}"
                f" | dimensions {latest.active_dimensions}"
            ),
        )
        painter.end()

    @staticmethod
    def _draw_axes(
        painter: QPainter,
        chart_rect: QRectF,
        *,
        first_generation: int,
        last_generation: int,
        y_max: float,
    ) -> None:
        metrics = QFontMetrics(painter.font())
        for index in range(5):
            ratio = index / 4.0
            y = chart_rect.bottom() - ratio * chart_rect.height()
            painter.setPen(QPen(QColor("#1B2C3F"), 1.0))
            painter.drawLine(
                QPointF(chart_rect.left(), y),
                QPointF(chart_rect.right(), y),
            )
            painter.setPen(QColor("#71869E"))
            painter.drawText(
                QRectF(
                    3.0,
                    y - metrics.height() / 2.0,
                    chart_rect.left() - 9.0,
                    metrics.height(),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_fixed(ratio * y_max),
            )

        for index in range(6):
            ratio = index / 5.0
            x = chart_rect.left() + ratio * chart_rect.width()
            painter.setPen(QPen(QColor("#142336"), 1.0))
            painter.drawLine(
                QPointF(x, chart_rect.top()),
                QPointF(x, chart_rect.bottom()),
            )
            generation = round(
                first_generation
                + ratio * (last_generation - first_generation)
            )
            painter.setPen(QColor("#71869E"))
            painter.drawText(
                QRectF(
                    x - 32.0,
                    chart_rect.bottom() + 5.0,
                    64.0,
                    metrics.height(),
                ),
                Qt.AlignmentFlag.AlignCenter,
                str(generation),
            )

        painter.setPen(QColor("#8FA2B8"))
        painter.drawText(
            QRectF(
                chart_rect.left(),
                chart_rect.bottom() + 22.0,
                chart_rect.width(),
                metrics.height(),
            ),
            Qt.AlignmentFlag.AlignCenter,
            "generation",
        )

    @staticmethod
    def _map_series(
        samples: tuple[PopulationDiversityPoint, ...],
        attribute: str,
        chart_rect: QRectF,
        *,
        first_generation: int,
        last_generation: int,
        y_max: float,
    ) -> list[QPointF]:
        points: list[QPointF] = []
        for sample in samples:
            x_ratio = (
                sample.generation_id - first_generation
            ) / (
                last_generation - first_generation
            )
            y_ratio = getattr(sample, attribute) / y_max
            points.append(
                QPointF(
                    chart_rect.left() + x_ratio * chart_rect.width(),
                    chart_rect.bottom() - y_ratio * chart_rect.height(),
                )
            )
        return points

    @staticmethod
    def _draw_line(
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
    ) -> None:
        if not points:
            return
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)

        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(points[-1], 2.8, 2.8)

    @staticmethod
    def _draw_current_generation_marker(
        painter: QPainter,
        chart_rect: QRectF,
        *,
        generation: int,
        first_generation: int,
        last_generation: int,
    ) -> None:
        ratio = (
            generation - first_generation
        ) / (
            last_generation - first_generation
        )
        x = chart_rect.left() + ratio * chart_rect.width()
        pen = QPen(QColor("#6C7F95"), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(x, chart_rect.top()),
            QPointF(x, chart_rect.bottom()),
        )

    @classmethod
    def _draw_legend(cls, painter: QPainter, chart_rect: QRectF) -> None:
        metrics = QFontMetrics(painter.font())
        labels = (
            ("spread", cls._SPREAD_COLOR),
            ("ellipse_area", cls._ELLIPSE_COLOR),
        )
        total_width = sum(
            28.0 + metrics.horizontalAdvance(label)
            for label, _color in labels
        ) + 14.0
        x = chart_rect.right() - total_width
        y = 3.0
        for label, color in labels:
            painter.setPen(QPen(color, 2.2))
            painter.drawLine(
                QPointF(x, y + 9.0),
                QPointF(x + 17.0, y + 9.0),
            )
            painter.setPen(QColor("#A4B4C6"))
            painter.drawText(
                QRectF(x + 22.0, y, metrics.horizontalAdvance(label) + 4.0, 19.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            x += 30.0 + metrics.horizontalAdvance(label)
