from __future__ import annotations

import time
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
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
    RunState,
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
from gow_monitor.ui.formatting import format_fixed
from gow_monitor.ui.widgets import (
    KpiCard,
    ObjectiveProgressChart,
    PopulationDiversityChart,
    ResourcesPanel,
    RunHealthPanel,
    SearchBehaviorPanel,
)


class OverviewPage(QWidget):
    """Dense live dashboard for the currently selected GOW run."""

    _TERMINAL_STATES = frozenset(
        {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.STOPPED,
        }
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._snapshot: RunSnapshot | None = None
        self._history: tuple[EvaluationPoint, ...] = ()
        self._runtime_completion_times: dict[str, float] = {}
        self._evaluation_detail_base = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

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
        description.setMaximumHeight(32)

        heading_row.addWidget(self.title_label)
        heading_row.addWidget(description, 1)

        cards_layout = QHBoxLayout()
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(6)

        self.cards = {
            "best": KpiCard("Best objective"),
            "evaluations": KpiCard("Evaluations"),
            "elapsed": KpiCard("Run time"),
            "improvement": KpiCard("Improvement rate"),
            "success": KpiCard("Success rate", visual="gauge"),
            "failures": KpiCard("Failure rate", visual="gauge"),
        }
        for card in self.cards.values():
            cards_layout.addWidget(card, 1)

        dashboard_layout = QHBoxLayout()
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(6)

        progress_panel = QFrame()
        progress_panel.setObjectName("dashboardPanel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(8, 6, 8, 6)
        progress_layout.setSpacing(4)

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
        self.diversity_title = QLabel("Diversity")
        self.diversity_title.setObjectName("panelTitle")
        self.diversity_chart = PopulationDiversityChart()
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
        progress_layout.addWidget(self.progress_chart, 3)
        progress_layout.addWidget(self.diversity_title)
        progress_layout.addWidget(self.diversity_chart, 2)
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
        self.lower_layout.setHorizontalSpacing(6)
        self.lower_layout.setVerticalSpacing(6)

        self.search_behavior_panel = SearchBehaviorPanel()
        self.resources_panel = ResourcesPanel()
        self._lower_panels_stacked: bool | None = None
        self._reflow_lower_panels(stacked=False)

        layout.addLayout(heading_row)
        layout.addLayout(cards_layout)
        layout.addLayout(dashboard_layout, 3)
        layout.addLayout(self.lower_layout, 2)

        self.runtime_timer = QTimer(self)
        self.runtime_timer.setInterval(1000)
        self.runtime_timer.timeout.connect(
            self._refresh_runtime_cards
        )

        self.clear()
        self.runtime_timer.start()

    @property
    def lower_panels_stacked(self) -> bool:
        return bool(self._lower_panels_stacked)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self._reflow_lower_panels(
            stacked=event.size().width() < 1100
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
        decimal_value = Decimal(str(value))
        if decimal_value == 0:
            return "0"

        decimal_text = format(decimal_value, "f")
        if "." in decimal_text:
            decimal_text = decimal_text.rstrip("0").rstrip(".")
        return decimal_text

    def render_snapshot(
        self,
        snapshot: RunSnapshot,
        history: tuple[EvaluationPoint, ...] = (),
    ) -> None:
        self._snapshot = snapshot
        self._history = history
        reference = snapshot.reference
        self._capture_runtime_completion(snapshot)

        improvement = recent_improvement_percent(
            history,
            reference.direction,
        )
        improvement_text = (
            format_fixed(improvement, suffix="%")
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
        if snapshot.planned_evaluations is not None:
            planned = snapshot.planned_evaluations
            evaluation_value = (
                f"{snapshot.evaluation_count:,} / {planned:,}"
            )
            completion = (
                snapshot.evaluation_count / planned * 100.0
                if planned
                else 0.0
            )
            evaluation_detail = (
                f"{format_fixed(completion, suffix='%')} completed"
                f" | {snapshot.result_sources} source(s)"
            )
        else:
            evaluation_value = f"{snapshot.evaluation_count:,}"
            evaluation_detail = (
                f"{snapshot.result_sources} distinct source(s)"
            )

        self._evaluation_detail_base = evaluation_detail
        self.cards["evaluations"].set_value(
            evaluation_value,
            detail=evaluation_detail,
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
            format_fixed(success_rate, suffix="%"),
            detail=f"{snapshot.successful_evaluations} valid objectives",
            tone="good" if snapshot.successful_evaluations else "warning",
            series=rolling_valid_rate_series(history),
            gauge_value=success_rate,
        )
        self.cards["failures"].set_value(
            format_fixed(failure_rate, suffix="%"),
            detail=f"{snapshot.failed_evaluations} failed evaluations",
            tone="bad" if snapshot.failed_evaluations else "good",
            series=rolling_failure_rate_series(history),
            gauge_value=failure_rate,
        )

        self._refresh_runtime_cards()

        self.progress_chart.set_history(history, reference.direction)
        self.diversity_chart.set_precomputed_series(
            snapshot.population_diversity
        )
        self.diversity_chart.set_history(history)
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

    def _refresh_runtime_cards(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return

        elapsed = self._elapsed_seconds(snapshot)
        if elapsed is None:
            self.cards["elapsed"].set_value(
                "N/A",
                detail="Timing data unavailable",
            )
            self._render_evaluation_rate(
                throughput=None,
                terminal=False,
            )
            return

        terminal = self._runtime_is_final(snapshot)
        elapsed_detail = "Final duration" if terminal else "Running"
        throughput = (
            snapshot.evaluation_count * 60.0 / elapsed
            if elapsed >= 1.0
            else None
        )

        self.cards["elapsed"].set_value(
            self._format_duration(elapsed),
            detail=elapsed_detail,
            tone="good" if terminal else "neutral",
        )
        self._render_evaluation_rate(
            throughput=throughput,
            terminal=terminal,
        )

    def _render_evaluation_rate(
        self,
        *,
        throughput: float | None,
        terminal: bool,
    ) -> None:
        if throughput is None:
            rate_text = "N/A eval/min"
        else:
            rate_text = format_fixed(
                throughput,
                suffix=" eval/min",
            )

        context = "final avg" if terminal else "live avg"
        secondary_line = f"{rate_text} | {context}"

        if self._evaluation_detail_base:
            detail = (
                f"{secondary_line}\n"
                f"{self._evaluation_detail_base}"
            )
        else:
            detail = secondary_line

        self.cards["evaluations"].detail_label.setText(detail)

    @staticmethod
    def _evaluation_target_reached(snapshot: RunSnapshot) -> bool:
        planned = snapshot.planned_evaluations
        return (
            planned is not None
            and planned > 0
            and snapshot.evaluation_count >= planned
        )

    def _capture_runtime_completion(
        self,
        snapshot: RunSnapshot,
    ) -> None:
        if not self._evaluation_target_reached(snapshot):
            return

        run_id = snapshot.reference.run_id
        if run_id in self._runtime_completion_times:
            return

        finished_at = snapshot.run_finished_at
        stop_time = (
            finished_at
            if finished_at is not None
            else time.time()
        )
        self._runtime_completion_times[run_id] = stop_time

    def _runtime_is_final(
        self,
        snapshot: RunSnapshot,
    ) -> bool:
        if self._evaluation_target_reached(snapshot):
            return True
        return snapshot.state in self._TERMINAL_STATES

    def _elapsed_seconds(
        self,
        snapshot: RunSnapshot,
    ) -> float | None:
        started_at = snapshot.run_started_at
        if started_at is None:
            return None

        self._capture_runtime_completion(snapshot)
        run_id = snapshot.reference.run_id

        if self._evaluation_target_reached(snapshot):
            end_time = self._runtime_completion_times[run_id]
        elif snapshot.state in self._TERMINAL_STATES:
            finished_at = snapshot.run_finished_at
            if finished_at is None:
                return None
            end_time = finished_at
        else:
            end_time = time.time()

        return max(0.0, end_time - started_at)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        days, remainder = divmod(total_seconds, 86_400)
        hours, remainder = divmod(remainder, 3_600)
        minutes, seconds_part = divmod(remainder, 60)

        clock = f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"
        return f"{days}d {clock}" if days else clock

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
        self._evaluation_detail_base = ""
        for card in self.cards.values():
            card.set_value("-", detail="Waiting for GOW artifacts")
        self.progress_chart.set_history((), ObjectiveDirection.UNKNOWN)
        self.diversity_chart.set_precomputed_series(())
        self.diversity_chart.set_history(())
        self.run_health_panel.clear()
        self.search_behavior_panel.clear()
        self.resources_panel.clear()
        self.chart_footer.setText(message)

    def _window_selection_changed(self, index: int) -> None:
        window_size = self.window_selector.itemData(index)
        if window_size is not None:
            window_size = int(window_size)
        self.progress_chart.set_window_size(window_size)
        self.diversity_chart.set_window_size(window_size)
