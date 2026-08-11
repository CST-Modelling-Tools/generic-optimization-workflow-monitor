from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gow_monitor.ui.widgets.semicircle_gauge import SemicircleGauge
from gow_monitor.ui.widgets.sparkline import SparklineWidget


class KpiCard(QFrame):
    """Compact Grafana-style value card with sparkline or half-dial gauge."""

    def __init__(
        self,
        title: str,
        *,
        visual: str = "sparkline",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if visual not in {"sparkline", "gauge"}:
            raise ValueError("visual must be 'sparkline' or 'gauge'")

        self.setObjectName("kpiCard")
        self.setProperty("kpiTone", "neutral")
        self.setProperty("kpiVisual", visual)
        self.setMinimumHeight(66)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("kpiTitle")

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(5)

        self.value_label = QLabel("-")
        self.value_label.setObjectName("kpiValue")
        self.value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.sparkline: SparklineWidget | None = None
        self.gauge: SemicircleGauge | None = None
        if visual == "gauge":
            self.gauge = SemicircleGauge()
            visual_widget: QWidget = self.gauge
        else:
            self.sparkline = SparklineWidget()
            visual_widget = self.sparkline

        value_row.addWidget(self.value_label, 1)
        value_row.addWidget(
            visual_widget,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("kpiDetail")
        self.detail_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addLayout(value_row)
        layout.addWidget(self.detail_label)

    def set_value(
        self,
        value: str,
        *,
        detail: str = "",
        tone: str = "neutral",
        series: Iterable[float] = (),
        gauge_value: float | None = None,
    ) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        if self.sparkline is not None:
            self.sparkline.set_values(series, tone=tone)
        if self.gauge is not None:
            self.gauge.set_value(gauge_value, tone=tone)
        self.setProperty("kpiTone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
