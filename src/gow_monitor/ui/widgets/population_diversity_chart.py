from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from gow_monitor.domain import EvaluationPoint
from gow_monitor.ui.dashboard_metrics import (
    PopulationDiversityPoint,
    population_diversity_series,
)
from gow_monitor.ui.formatting import format_fixed
from gow_monitor.ui.widgets.chart_navigation import HorizontalZoom


class PopulationDiversityChart(QWidget):
    """Native dual-series diversity chart inspired by GOW diagnostics."""

    _SPREAD_COLOR = QColor("#4D8DFF")
    _ELLIPSE_COLOR = QColor("#FF9F43")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: tuple[EvaluationPoint, ...] = ()
        self._precomputed: tuple[PopulationDiversityPoint, ...] = ()
        self._window_size: int | None = None
        self._navigation = HorizontalZoom()
        self._interactive_navigation = False
        self._drag_anchor_x: float | None = None
        self._drag_origin_x: float | None = None
        self._drag_moved = False
        self._selected_inspection: tuple[str, int, int] | None = None
        self.setMinimumHeight(118)
        self.setToolTip(
            "spread: sum of marginal sample standard deviations in normalized "
            "parameter space. ellipse_area: area of the 95% confidence ellipse "
            "in the two dominant PCA directions."
        )

    def sizeHint(self) -> QSize:
        return QSize(420, 145)

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
        if window_size == self._window_size:
            return
        self._window_size = window_size
        self._navigation.reset()
        self.update()

    def _base_visible_samples(
        self,
    ) -> tuple[PopulationDiversityPoint, ...]:
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

    def visible_samples(self) -> tuple[PopulationDiversityPoint, ...]:
        samples = self._base_visible_samples()
        first, last = self._navigation.slice_bounds(len(samples))
        return samples[first:last]

    @property
    def interactive_navigation(self) -> bool:
        return self._interactive_navigation

    @property
    def zoom_active(self) -> bool:
        return self._navigation.active

    @property
    def selected_inspection(
        self,
    ) -> tuple[str, int, int] | None:
        return self._selected_inspection

    def clear_inspection(self) -> None:
        self._selected_inspection = None
        self.update()

    def set_interactive_navigation(self, enabled: bool) -> None:
        self._interactive_navigation = bool(enabled)
        cursor = (
            Qt.CursorShape.OpenHandCursor
            if self._interactive_navigation
            else Qt.CursorShape.ArrowCursor
        )
        self.setCursor(cursor)

    def reset_view(self) -> None:
        self._navigation.reset()
        self.update()

    def zoom_in(self, anchor: float = 0.5) -> None:
        self._navigation.zoom_at(anchor, 0.72)
        self.update()

    def zoom_out(self, anchor: float = 0.5) -> None:
        self._navigation.zoom_at(anchor, 1.0 / 0.72)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._interactive_navigation:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        plot_width = max(10.0, self.width() - 70.0)
        anchor = (event.position().x() - 54.0) / plot_width
        anchor = min(1.0, max(0.0, anchor))

        if delta > 0:
            self.zoom_in(anchor)
        else:
            self.zoom_out(anchor)

        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self._interactive_navigation
            and event.button() is Qt.MouseButton.LeftButton
        ):
            position_x = event.position().x()
            self._drag_anchor_x = position_x
            self._drag_origin_x = position_x
            self._drag_moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._interactive_navigation
            and self._drag_anchor_x is not None
        ):
            current_x = event.position().x()
            if (
                self._drag_origin_x is not None
                and abs(current_x - self._drag_origin_x) >= 4.0
            ):
                self._drag_moved = True

            if self._drag_moved:
                plot_width = max(10.0, self.width() - 70.0)
                delta_fraction = (
                    self._drag_anchor_x - current_x
                ) / plot_width
                self._navigation.pan_display_fraction(
                    delta_fraction
                )
                self._drag_anchor_x = current_x
                self.update()

            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._interactive_navigation
            and event.button() is Qt.MouseButton.LeftButton
        ):
            was_click = not self._drag_moved
            self._drag_anchor_x = None
            self._drag_origin_x = None
            self._drag_moved = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

            if was_click:
                self.inspect_at(event.position())

            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            self._interactive_navigation
            and event.button() is Qt.MouseButton.LeftButton
        ):
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0A121E"))

        chart_rect = QRectF(
            54.0,
            28.0,
            max(10.0, self.width() - 70.0),
            max(10.0, self.height() - 60.0),
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
                f"spread {format_fixed(latest.spread)}"
                f"   |   ellipse {format_fixed(latest.ellipse_area)}"
            ),
        )
        self._draw_inspection(
            painter,
            chart_rect,
            samples,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
            y_max=y_max,
        )
        painter.end()

    def inspect_at(self, position: QPointF) -> bool:
        if not self._interactive_navigation:
            return False

        chart_rect = QRectF(
            54.0,
            28.0,
            max(10.0, self.width() - 70.0),
            max(10.0, self.height() - 60.0),
        )

        if not chart_rect.adjusted(
            -12.0,
            -12.0,
            12.0,
            12.0,
        ).contains(position):
            self.clear_inspection()
            return False

        samples = self.visible_samples()
        if not samples:
            self.clear_inspection()
            return False

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

        candidates = self._inspection_candidates(
            chart_rect,
            samples,
            first_generation=first_generation,
            last_generation=mapped_last_generation,
            y_max=y_max,
        )
        if not candidates:
            self.clear_inspection()
            return False

        nearest = min(
            candidates,
            key=lambda candidate: (
                (candidate[3].x() - position.x()) ** 2
                + (candidate[3].y() - position.y()) ** 2
            ),
        )
        distance_squared = (
            (nearest[3].x() - position.x()) ** 2
            + (nearest[3].y() - position.y()) ** 2
        )

        if distance_squared > 20.0**2:
            self.clear_inspection()
            return False

        self._selected_inspection = (
            nearest[0],
            nearest[1].generation_id,
            nearest[1].evaluation,
        )
        self.update()
        return True

    def _inspection_candidates(
        self,
        chart_rect: QRectF,
        samples: tuple[PopulationDiversityPoint, ...],
        *,
        first_generation: int,
        last_generation: int,
        y_max: float,
    ) -> list[
        tuple[
            str,
            PopulationDiversityPoint,
            float,
            QPointF,
            QColor,
        ]
    ]:
        candidates: list[
            tuple[
                str,
                PopulationDiversityPoint,
                float,
                QPointF,
                QColor,
            ]
        ] = []

        specs = (
            ("Spread", "spread", self._SPREAD_COLOR),
            ("Ellipse", "ellipse_area", self._ELLIPSE_COLOR),
        )

        for label, attribute, color in specs:
            mapped = self._map_series(
                samples,
                attribute,
                chart_rect,
                first_generation=first_generation,
                last_generation=last_generation,
                y_max=y_max,
            )
            for sample, point in zip(samples, mapped, strict=True):
                candidates.append(
                    (
                        label,
                        sample,
                        getattr(sample, attribute),
                        point,
                        QColor(color),
                    )
                )

        return candidates

    def _draw_inspection(
        self,
        painter: QPainter,
        chart_rect: QRectF,
        samples: tuple[PopulationDiversityPoint, ...],
        *,
        first_generation: int,
        last_generation: int,
        y_max: float,
    ) -> None:
        selection = self._selected_inspection
        if selection is None:
            return

        candidates = self._inspection_candidates(
            chart_rect,
            samples,
            first_generation=first_generation,
            last_generation=last_generation,
            y_max=y_max,
        )

        selected = next(
            (
                candidate
                for candidate in candidates
                if (
                    candidate[0],
                    candidate[1].generation_id,
                    candidate[1].evaluation,
                )
                == selection
            ),
            None,
        )
        if selected is None:
            return

        label, sample, value, mapped, color = selected

        guide_color = QColor(color)
        guide_color.setAlpha(75)
        painter.setPen(
            QPen(
                guide_color,
                1.0,
                Qt.PenStyle.DotLine,
            )
        )
        painter.drawLine(
            QPointF(mapped.x(), chart_rect.top()),
            QPointF(mapped.x(), chart_rect.bottom()),
        )

        painter.setPen(QPen(QColor("#EAF2FA"), 2.0))
        painter.setBrush(color)
        painter.drawEllipse(mapped, 6.0, 6.0)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#EAF2FA"))
        painter.drawEllipse(mapped, 2.2, 2.2)

        lines = (
            f"Generation: {sample.generation_id}",
            f"Evaluation: {sample.evaluation}",
            f"Metric: {label}",
            f"Value: {self._format_inspection_value(value)}",
            (
                f"Population: {sample.population_size}"
                f"   |   Dimensions: {sample.active_dimensions}"
            ),
        )
        self._draw_inspection_box(
            painter,
            chart_rect,
            mapped,
            lines,
            color,
        )

    @staticmethod
    def _format_inspection_value(value: float) -> str:
        return f"{value:.17g}"

    @staticmethod
    def _draw_inspection_box(
        painter: QPainter,
        chart_rect: QRectF,
        anchor: QPointF,
        lines: tuple[str, ...],
        accent: QColor,
    ) -> None:
        metrics = QFontMetrics(painter.font())
        line_height = metrics.height() + 3.0
        box_width = 300.0
        box_height = 14.0 + line_height * len(lines)

        x = anchor.x() + 14.0
        if x + box_width > chart_rect.right() - 6.0:
            x = anchor.x() - box_width - 14.0
        x = max(
            chart_rect.left() + 6.0,
            min(x, chart_rect.right() - box_width - 6.0),
        )

        y = anchor.y() - box_height - 14.0
        if y < chart_rect.top() + 6.0:
            y = anchor.y() + 14.0
        y = max(
            chart_rect.top() + 6.0,
            min(y, chart_rect.bottom() - box_height - 6.0),
        )

        box = QRectF(x, y, box_width, box_height)

        painter.setPen(QPen(accent, 1.2))
        painter.setBrush(QColor(9, 19, 31, 242))
        painter.drawRoundedRect(box, 6.0, 6.0)

        painter.setPen(QColor("#EAF2FA"))
        text_y = box.top() + 7.0
        for line in lines:
            painter.drawText(
                QRectF(
                    box.left() + 10.0,
                    text_y,
                    box.width() - 20.0,
                    line_height,
                ),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter,
                line,
            )
            text_y += line_height

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
            ("Spread", cls._SPREAD_COLOR),
            ("Ellipse", cls._ELLIPSE_COLOR),
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
