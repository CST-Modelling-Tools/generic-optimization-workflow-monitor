from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gow_monitor.domain import (
    EvaluationPoint,
    GowProcessResourceSnapshot,
    ObjectiveDirection,
    RunSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.ui.dashboard_metrics import (
    best_series,
    cumulative_evaluations_series,
    recent_improvement_percent,
    recent_improvement_series,
    rolling_failure_rate_series,
    rolling_valid_rate_series,
)
from gow_monitor.ui.widgets import (
    KpiCard,
    ObjectiveProgressChart,
    ResourcesPanel,
    RunHealthPanel,
    SearchBehaviorPanel,
)


class OverviewPage(QWidget):
    """Dense live dashboard for the currently selected GOW run."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._snapshot: RunSnapshot | None = None
        self._history: tuple[EvaluationPoint, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(9)

        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(12)

        self.title_label = QLabel("Overview")
        self.title_label.setObjectName("pageTitle")
        description = QLabel(
            "Live metrics calculated only from observable GOW artifacts."
        )
        description.setObjectName("description")
        description.setWordWrap(True)

        heading_row.addWidget(self.title_label)
        heading_row.addWidget(description, 1)

        cards_layout = QHBoxLayout()
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(9)

        self.cards = {
            "best": KpiCard("Best objective"),
            "evaluations": KpiCard("Evaluations"),
            "improvement": KpiCard("Improvement rate"),
            "success": KpiCard("Success rate", visual="gauge"),
            "failures": KpiCard("Failure rate", visual="gauge"),
        }
        for card in self.cards.values():
            cards_layout.addWidget(card, 1)

        dashboard_layout = QHBoxLayout()
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(9)

        progress_panel = QFrame()
        progress_panel.setObjectName("dashboardPanel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(11, 9, 11, 9)
        progress_layout.setSpacing(7)

        progress_header = QHBoxLayout()
        progress_header.setContentsMargins(0, 0, 0, 0)
        progress_title = QLabel("Optimization progress")
        progress_title.setObjectName("panelTitle")

        self.window_selector = QComboBox()
        self.window_selector.setObjectName("windowSelector")
        self.window_selector.addItem("All evaluations", None)
        self.window_selector.addItem("Last 500", 500)
        self.window_selector.addItem("Last 100", 100)
        self.window_selector.currentIndexChanged.connect(
            self._window_selection_changed
        )

        progress_header.addWidget(progress_title)
        progress_header.addStretch(1)
        progress_header.addWidget(self.window_selector)

        self.progress_chart = ObjectiveProgressChart()
        self.chart_meta_bar = QFrame()
        self.chart_meta_bar.setObjectName("chartMetaBar")
        chart_meta_layout = QHBoxLayout(self.chart_meta_bar)
        chart_meta_layout.setContentsMargins(8, 4, 8, 4)
        self.chart_footer = QLabel("No GOW run connected")
        self.chart_footer.setObjectName("chartFooter")
        self.chart_footer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.chart_footer.setWordWrap(False)
        chart_meta_layout.addWidget(self.chart_footer)

        progress_layout.addLayout(progress_header)
        progress_layout.addWidget(self.progress_chart, 1)
        progress_layout.addWidget(self.chart_meta_bar)

        self.run_health_panel = RunHealthPanel()

        dashboard_layout.addWidget(progress_panel, 3)
        dashboard_layout.addWidget(
            self.run_health_panel,
            1,
            Qt.AlignmentFlag.AlignTop,
        )

        self.lower_layout = QGridLayout()
        self.lower_layout.setContentsMargins(0, 0, 0, 0)
        self.lower_layout.setHorizontalSpacing(9)
        self.lower_layout.setVerticalSpacing(9)

        self.search_behavior_panel = SearchBehaviorPanel()
        self.resources_panel = ResourcesPanel()
        self._lower_panels_stacked: bool | None = None
        self._reflow_lower_panels(stacked=False)

        layout.addLayout(heading_row)
        layout.addLayout(cards_layout)
        layout.addLayout(dashboard_layout, 3)
        layout.addLayout(self.lower_layout, 2)

        self.clear()

    @property
    def lower_panels_stacked(self) -> bool:
        return bool(self._lower_panels_stacked)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self._reflow_lower_panels(
            stacked=event.size().width() < 1180
        )

    def _reflow_lower_panels(
        self,
        *,
        stacked: bool,
    ) -> None:
        if self._lower_panels_stacked == stacked:
            return

        self.lower_layout.removeWidget(
            self.search_behavior_panel
        )
        self.lower_layout.removeWidget(
            self.resources_panel
        )

        for row in range(2):
            self.lower_layout.setRowStretch(row, 0)

        for column in range(2):
            self.lower_layout.setColumnStretch(column, 0)

        if stacked:
            self.lower_layout.addWidget(
                self.search_behavior_panel,
                0,
                0,
            )
            self.lower_layout.addWidget(
                self.resources_panel,
                1,
                0,
            )
            self.lower_layout.setColumnStretch(0, 1)
        else:
            self.lower_layout.addWidget(
                self.search_behavior_panel,
                0,
                0,
            )
            self.lower_layout.addWidget(
                self.resources_panel,
                0,
                1,
            )
            self.lower_layout.setColumnStretch(0, 4)
            self.lower_layout.setColumnStretch(1, 6)

        self._lower_panels_stacked = stacked
        self.updateGeometry()

    @staticmethod
    def _format_objective(value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:.12g}"

    def render_snapshot(
        self,
        snapshot: RunSnapshot,
        history: tuple[EvaluationPoint, ...] = (),
    ) -> None:
        self._snapshot = snapshot
        self._history = history
        reference = snapshot.reference

        improvement = recent_improvement_percent(
            history,
            reference.direction,
        )
        improvement_text = (
            f"{improvement:.4g}%"
            if improvement is not None
            else "N/A"
        )
        success_rate = snapshot.success_rate * 100.0
        failure_rate = snapshot.failure_rate * 100.0

        self.cards["best"].set_value(
            self._format_objective(snapshot.best_objective),
            detail=reference.direction.value,
            tone="good" if snapshot.best_objective is not None else "neutral",
            series=best_series(history),
        )
        self.cards["evaluations"].set_value(
            f"{snapshot.evaluation_count:,}",
            detail=f"{snapshot.result_sources} distinct source(s)",
            series=cumulative_evaluations_series(history),
        )
        self.cards["improvement"].set_value(
            improvement_text,
            detail="Over last 100 evaluations",
            tone=(
                "good"
                if improvement is not None and improvement > 0.0
                else "neutral"
            ),
            series=recent_improvement_series(history, reference.direction),
        )
        self.cards["success"].set_value(
            f"{success_rate:.2f}%",
            detail=f"{snapshot.successful_evaluations} valid objectives",
            tone="good" if snapshot.successful_evaluations else "warning",
            series=rolling_valid_rate_series(history),
            gauge_value=success_rate,
        )
        self.cards["failures"].set_value(
            f"{failure_rate:.2f}%",
            detail=f"{snapshot.failed_evaluations} failed evaluations",
            tone="bad" if snapshot.failed_evaluations else "good",
            series=rolling_failure_rate_series(history),
            gauge_value=failure_rate,
        )

        self.progress_chart.set_history(history, reference.direction)
        self.run_health_panel.render(snapshot, history)
        self.search_behavior_panel.render(snapshot, history)
        self.resources_panel.render(snapshot)

        best_candidate = snapshot.best_candidate_id or "-"
        self.chart_footer.setText(
            f"Best candidate: {best_candidate}   |   "
            f"Problem: {reference.problem_id or 'unknown'}   |   "
            f"Evaluations: {snapshot.evaluation_count:,}"
        )
        self.chart_footer.setToolTip(str(reference.run_root))

    def render_resource_snapshot(
        self,
        snapshot: SystemResourceSnapshot,
        history: tuple[SystemResourceSnapshot, ...] = (),
    ) -> None:
        self.resources_panel.render_system(snapshot, history)

    def render_resource_error(self, message: str) -> None:
        self.resources_panel.render_system_error(message)

    def render_gow_resource_snapshot(
        self,
        snapshot: GowProcessResourceSnapshot,
        history: tuple[GowProcessResourceSnapshot, ...] = (),
    ) -> None:
        self.resources_panel.render_gow_process(snapshot, history)

    def render_gow_resource_error(self, message: str) -> None:
        self.resources_panel.render_gow_process_error(message)

    def clear(self, message: str = "No GOW run connected") -> None:
        self._snapshot = None
        self._history = ()
        for card in self.cards.values():
            card.set_value("-", detail="Waiting for GOW artifacts")
        self.progress_chart.set_history((), ObjectiveDirection.UNKNOWN)
        self.run_health_panel.clear()
        self.search_behavior_panel.clear()
        self.resources_panel.clear()
        self.chart_footer.setText(message)

    def _window_selection_changed(self, index: int) -> None:
        window_size = self.window_selector.itemData(index)
        if window_size is not None:
            window_size = int(window_size)
        self.progress_chart.set_window_size(window_size)
