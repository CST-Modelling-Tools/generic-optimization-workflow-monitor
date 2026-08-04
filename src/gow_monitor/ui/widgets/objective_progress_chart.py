from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from gow_monitor.domain import EvaluationPoint, ObjectiveDirection


class ObjectiveProgressChart(QWidget):
    """Native Qt chart focused on incumbent, median and mean evolution."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: tuple[EvaluationPoint, ...] = ()
        self._direction = ObjectiveDirection.UNKNOWN
        self._window_size: int | None = None
        self.setMinimumHeight(260)
        self.setToolTip(
            "Best-so-far, cumulative median, cumulative mean and failed "
            "evaluations. Positive high-dynamic-range data uses log scale."
        )

    def sizeHint(self) -> QSize:
        return QSize(760, 310)

    @property
    def history(self) -> tuple[EvaluationPoint, ...]:
        return self._history

    @property
    def window_size(self) -> int | None:
        return self._window_size

    def set_history(
        self,
        history: Iterable[EvaluationPoint],
        direction: ObjectiveDirection,
    ) -> None:
        self._history = tuple(history)
        self._direction = direction
        self.update()

    def set_window_size(self, window_size: int | None) -> None:
        if window_size is not None and window_size < 2:
            raise ValueError("window_size must be at least 2")
        self._window_size = window_size
        self.update()

    def visible_points(self) -> tuple[EvaluationPoint, ...]:
        if self._window_size is None:
            return self._history
        return self._history[-self._window_size :]

    def effective_scale(self) -> str:
        values = self._numeric_values(self.visible_points())
        return self._select_scale(values)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0A121E"))

        chart_rect = QRectF(
            70.0,
            44.0,
            max(10.0, self.width() - 92.0),
            max(10.0, self.height() - 94.0),
        )
        self._draw_frame(painter, chart_rect)

        points = self.visible_points()
        numeric_values = self._numeric_values(points)
        if not points or not numeric_values:
            self._draw_empty_state(painter, chart_rect)
            painter.end()
            return

        scale = self._select_scale(numeric_values)
        transformed_values = [
            self._transform_value(value, scale)
            for value in numeric_values
        ]
        y_min, y_max = self._expanded_bounds(
            transformed_values,
            clamp_zero=scale == "linear",
        )
        x_min = points[0].evaluation
        x_max = points[-1].evaluation
        if x_min == x_max:
            x_max = x_min + 1

        self._draw_axis_caption(painter, chart_rect, scale)
        self._draw_grid_and_axes(
            painter,
            chart_rect,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            scale=scale,
        )
        self._draw_series(
            painter,
            chart_rect,
            points,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            scale=scale,
        )
        self._draw_legend(painter, chart_rect)
        painter.end()

    @staticmethod
    def _numeric_values(points: Iterable[EvaluationPoint]) -> list[float]:
        values: list[float] = []
        for point in points:
            for value in (
                point.best_so_far,
                point.median_so_far,
                point.mean_so_far,
            ):
                if value is not None and math.isfinite(value):
                    values.append(value)
        return values

    @staticmethod
    def _select_scale(values: list[float]) -> str:
        if not values or min(values) <= 0.0:
            return "linear"
        ratio = max(values) / min(values)
        return "log" if ratio >= 250.0 else "linear"

    @staticmethod
    def _transform_value(value: float, scale: str) -> float:
        if scale == "log":
            return math.log10(value)
        return value

    @staticmethod
    def _inverse_value(value: float, scale: str) -> float:
        if scale == "log":
            return 10.0**value
        return value

    @staticmethod
    def _expanded_bounds(
        values: list[float],
        *,
        clamp_zero: bool = True,
    ) -> tuple[float, float]:
        if not values:
            raise ValueError("values cannot be empty")

        y_min = min(values)
        y_max = max(values)
        if y_min == y_max:
            padding = max(abs(y_min) * 0.05, 1e-9)
            lower = y_min - padding
            upper = y_max + padding
        else:
            padding = (y_max - y_min) * 0.08
            lower = y_min - padding
            upper = y_max + padding

        if clamp_zero and y_min >= 0.0:
            lower = max(0.0, lower)
        if clamp_zero and y_max <= 0.0:
            upper = min(0.0, upper)
        if lower == upper:
            upper = lower + 1.0
        return lower, upper

    @staticmethod
    def _draw_frame(painter: QPainter, chart_rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#22364B"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(chart_rect, 4.0, 4.0)

    @staticmethod
    def _draw_empty_state(painter: QPainter, chart_rect: QRectF) -> None:
        painter.setPen(QColor("#7890A9"))
        painter.drawText(
            chart_rect,
            Qt.AlignmentFlag.AlignCenter,
            "No objective history available",
        )

    def _draw_axis_caption(
        self,
        painter: QPainter,
        chart_rect: QRectF,
        scale: str,
    ) -> None:
        direction = (
            "maximize"
            if self._direction is ObjectiveDirection.MAXIMIZE
            else "minimize"
        )
        scale_suffix = " | LOG" if scale == "log" else ""
        painter.setPen(QColor("#71869E"))
        painter.drawText(
            QRectF(chart_rect.left(), 4.0, 250.0, 18.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"Objective value ({direction}){scale_suffix}",
        )

    def _draw_grid_and_axes(
        self,
        painter: QPainter,
        chart_rect: QRectF,
        *,
        x_min: int,
        x_max: int,
        y_min: float,
        y_max: float,
        scale: str,
    ) -> None:
        metrics = QFontMetrics(painter.font())
        horizontal_pen = QPen(QColor("#1B2C3F"), 1.0)
        vertical_pen = QPen(QColor("#142336"), 1.0)
        text_pen = QPen(QColor("#71869E"), 1.0)

        for index in range(6):
            ratio = index / 5.0
            y = chart_rect.bottom() - ratio * chart_rect.height()
            painter.setPen(horizontal_pen)
            painter.drawLine(
                QPointF(chart_rect.left(), y),
                QPointF(chart_rect.right(), y),
            )
            transformed = y_min + ratio * (y_max - y_min)
            value = self._inverse_value(transformed, scale)
            label = self._format_axis_value(value)
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(
                    4.0,
                    y - metrics.height() / 2.0,
                    chart_rect.left() - 10.0,
                    metrics.height(),
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        for index in range(6):
            ratio = index / 5.0
            x = chart_rect.left() + ratio * chart_rect.width()
            painter.setPen(vertical_pen)
            painter.drawLine(
                QPointF(x, chart_rect.top()),
                QPointF(x, chart_rect.bottom()),
            )
            evaluation = round(x_min + ratio * (x_max - x_min))
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(
                    x - 38.0,
                    chart_rect.bottom() + 8.0,
                    76.0,
                    metrics.height(),
                ),
                Qt.AlignmentFlag.AlignCenter,
                str(evaluation),
            )

        painter.setPen(QColor("#8FA2B8"))
        painter.drawText(
            QRectF(
                chart_rect.left(),
                chart_rect.bottom() + 28.0,
                chart_rect.width(),
                metrics.height(),
            ),
            Qt.AlignmentFlag.AlignCenter,
            "Evaluation",
        )

    def _draw_series(
        self,
        painter: QPainter,
        chart_rect: QRectF,
        points: tuple[EvaluationPoint, ...],
        *,
        x_min: int,
        x_max: int,
        y_min: float,
        y_max: float,
        scale: str,
    ) -> None:
        best_points = self._series_points(
            points,
            "best_so_far",
            chart_rect,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            scale=scale,
        )
        if best_points:
            self._draw_best_fill(painter, chart_rect, best_points)

        series = (
            ("mean_so_far", QColor("#8295A8"), 1.2, Qt.PenStyle.DotLine),
            ("median_so_far", QColor("#A17AF0"), 1.6, Qt.PenStyle.DashLine),
            ("best_so_far", QColor("#4D8DFF"), 3.0, Qt.PenStyle.SolidLine),
        )

        for attribute, color, width, style in series:
            mapped_points = self._series_points(
                points,
                attribute,
                chart_rect,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                scale=scale,
            )
            if not mapped_points:
                continue
            path = self._path_from_points(mapped_points)
            pen = QPen(color, width)
            pen.setStyle(style)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if best_points:
            painter.setPen(QPen(QColor("#DCE6F2"), 1.2))
            painter.setBrush(QColor("#4D8DFF"))
            painter.drawEllipse(best_points[-1], 3.4, 3.4)

        failed_pen = QPen(QColor("#FF6B78"), 1.7)
        painter.setPen(failed_pen)
        marker_y = chart_rect.bottom() - 6.0
        for point in points:
            if point.status == "ok":
                continue
            x = self._map_x(
                point.evaluation,
                chart_rect,
                x_min=x_min,
                x_max=x_max,
            )
            painter.drawLine(
                QPointF(x - 3.0, marker_y - 3.0),
                QPointF(x + 3.0, marker_y + 3.0),
            )
            painter.drawLine(
                QPointF(x - 3.0, marker_y + 3.0),
                QPointF(x + 3.0, marker_y - 3.0),
            )

    @staticmethod
    def _draw_best_fill(
        painter: QPainter,
        chart_rect: QRectF,
        points: list[QPointF],
    ) -> None:
        path = ObjectiveProgressChart._path_from_points(points)
        path.lineTo(points[-1].x(), chart_rect.bottom())
        path.lineTo(points[0].x(), chart_rect.bottom())
        path.closeSubpath()

        gradient = QLinearGradient(0.0, chart_rect.top(), 0.0, chart_rect.bottom())
        gradient.setColorAt(0.0, QColor(77, 141, 255, 55))
        gradient.setColorAt(1.0, QColor(77, 141, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)

    def _series_points(
        self,
        points: tuple[EvaluationPoint, ...],
        attribute: str,
        chart_rect: QRectF,
        *,
        x_min: int,
        x_max: int,
        y_min: float,
        y_max: float,
        scale: str,
    ) -> list[QPointF]:
        mapped: list[QPointF] = []
        for point in points:
            value = getattr(point, attribute)
            if value is None:
                continue
            x = self._map_x(
                point.evaluation,
                chart_rect,
                x_min=x_min,
                x_max=x_max,
            )
            y = self._map_y(
                value,
                chart_rect,
                y_min=y_min,
                y_max=y_max,
                scale=scale,
            )
            mapped.append(QPointF(x, y))
        return mapped

    @staticmethod
    def _path_from_points(points: list[QPointF]) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        return path

    @staticmethod
    def _map_x(
        evaluation: int,
        chart_rect: QRectF,
        *,
        x_min: int,
        x_max: int,
    ) -> float:
        ratio = (evaluation - x_min) / (x_max - x_min)
        return chart_rect.left() + ratio * chart_rect.width()

    @classmethod
    def _map_y(
        cls,
        value: float,
        chart_rect: QRectF,
        *,
        y_min: float,
        y_max: float,
        scale: str = "linear",
    ) -> float:
        transformed = cls._transform_value(value, scale)
        ratio = (transformed - y_min) / (y_max - y_min)
        return chart_rect.bottom() - ratio * chart_rect.height()

    def _draw_legend(self, painter: QPainter, chart_rect: QRectF) -> None:
        legend_items = (
            ("Best-so-far", QColor("#4D8DFF")),
            ("Median", QColor("#A17AF0")),
            ("Mean", QColor("#8295A8")),
            ("Failed", QColor("#FF6B78")),
        )
        x = chart_rect.left() + 250.0
        y = 4.0
        metrics = QFontMetrics(painter.font())

        for label, color in legend_items:
            painter.setPen(QPen(color, 2.0))
            painter.drawLine(QPointF(x, y + 9.0), QPointF(x + 16.0, y + 9.0))
            painter.setPen(QColor("#91A4B9"))
            painter.drawText(
                QRectF(x + 21.0, y, 100.0, metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            x += 28.0 + metrics.horizontalAdvance(label)

    @staticmethod
    def _format_axis_value(value: float) -> str:
        magnitude = abs(value)
        if magnitude != 0.0 and (magnitude >= 10000.0 or magnitude < 0.001):
            return f"{value:.2e}"
        if magnitude >= 100.0:
            return f"{value:.1f}"
        if magnitude >= 1.0:
            return f"{value:.3f}"
        return f"{value:.5f}"
