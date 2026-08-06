from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gow_monitor.domain import (
    EvaluationPoint,
    GowProcessResourceSnapshot,
    RunSnapshot,
    RunState,
    SystemResourceSnapshot,
)
from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.live_refresh import LiveRefreshController, LiveRefreshPayload
from gow_monitor.ui.pages import OverviewPage
from gow_monitor.ui.resource_monitor import ResourceMonitorController

NAVIGATION_ITEMS = (
    ("Overview", "Overview"),
    ("Progress", "Optimization Progress"),
    ("Search Behavior", "Search Behavior"),
    ("Resources", "Resources Utilization"),
    ("Alerts", "Run Alerts"),
    ("Provenance", "Run Provenance"),
    ("Configuration", "Configuration"),
)

AUTO_REFRESH_INTERVAL_MS = 1000


class MainWindow(QMainWindow):
    """Top-level desktop shell for the independent monitor."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        gow_pid: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.navigation_buttons: dict[str, QPushButton] = {}
        self.page_titles: dict[str, QLabel] = {}
        self.placeholder_labels: dict[str, QLabel] = {}
        self._reader: GowFilesystemRunReader | None = None
        self._snapshots: tuple[RunSnapshot, ...] = ()
        self._histories: dict[str, tuple[EvaluationPoint, ...]] = {}
        self._connected_path: Path | None = None
        self._resource_history: deque[SystemResourceSnapshot] = deque(
            maxlen=60
        )
        self._gow_resource_history: deque[
            GowProcessResourceSnapshot
        ] = deque(maxlen=60)

        self.live_refresh = LiveRefreshController(
            self,
            interval_ms=AUTO_REFRESH_INTERVAL_MS,
        )
        self.live_refresh.refresh_started.connect(self._refresh_started)
        self.live_refresh.refreshed.connect(self._refresh_completed)
        self.live_refresh.refresh_failed.connect(self._refresh_failed)

        self.resource_monitor = ResourceMonitorController(
            self,
            interval_ms=AUTO_REFRESH_INTERVAL_MS,
            gow_pid=gow_pid,
        )
        self.resource_monitor.sampled.connect(self._resource_sampled)
        self.resource_monitor.sample_failed.connect(self._resource_failed)
        self.resource_monitor.gow_sampled.connect(
            self._gow_resource_sampled
        )
        self.resource_monitor.gow_sample_failed.connect(
            self._gow_resource_failed
        )

        self.setWindowTitle("GOW Monitor")
        self.resize(1440, 900)
        self.setMinimumSize(1280, 760)

        self._build_ui()
        self._apply_style()
        self.select_page("Overview")
        self._render_no_run()

    @property
    def current_snapshot(self) -> RunSnapshot | None:
        index = self.run_selector.currentIndex()
        if index < 0 or index >= len(self._snapshots):
            return None
        return self._snapshots[index]

    @property
    def current_history(self) -> tuple[EvaluationPoint, ...]:
        snapshot = self.current_snapshot
        if snapshot is None:
            return ()
        return self._histories.get(snapshot.reference.run_id, ())

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        self.sidebar.setVisible(False)
        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(8)

        self.brand_label = QLabel("GOW")
        brand = self.brand_label
        brand.setObjectName("brand")
        subtitle = QLabel("Optimization Monitor")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        for key, _title in NAVIGATION_ITEMS:
            button = QPushButton(key)
            button.setObjectName("navigationButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, page_key=key: self.select_page(page_key)
            )
            self.navigation_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        info_title = QLabel("Job info")
        info_title.setObjectName("sidebarSectionTitle")
        layout.addWidget(info_title)

        self.sidebar_run_id = QLabel("Run: -")
        self.sidebar_problem = QLabel("Problem: -")
        self.sidebar_evaluations = QLabel("Evaluations: 0")
        self.sidebar_failures = QLabel("Failures: 0")

        for label in (
            self.sidebar_run_id,
            self.sidebar_problem,
            self.sidebar_evaluations,
            self.sidebar_failures,
        ):
            label.setObjectName("sidebarInfo")
            label.setWordWrap(True)
            layout.addWidget(label)

        layout.addSpacing(12)
        self.version_label = QLabel("Framework foundation | v0.1.0")
        version = self.version_label
        version.setObjectName("sidebarFooter")
        version.setWordWrap(True)
        layout.addWidget(version)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 7, 12, 7)
        header_layout.setSpacing(10)

        self.job_label = QLabel("Job: No run selected")
        self.job_label.setObjectName("jobTitle")

        self.run_selector = QComboBox()
        self.run_selector.setObjectName("runSelector")
        self.run_selector.setMinimumWidth(220)
        self.run_selector.setEnabled(False)
        self.run_selector.currentIndexChanged.connect(self._selected_run_changed)

        self.open_results_button = QPushButton("Open GOW results")
        self.open_results_button.setObjectName("primaryButton")
        self.open_results_button.clicked.connect(self._choose_results_root)

        self.auto_refresh_label = QLabel("AUTO OFF")
        self.auto_refresh_label.setObjectName("refreshBadge")
        self.auto_refresh_label.setProperty("refreshState", "off")
        self.auto_refresh_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auto_refresh_label.setMinimumWidth(82)

        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("stateBadge")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumWidth(92)

        header_layout.addWidget(self.job_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.run_selector)
        header_layout.addWidget(self.open_results_button)
        header_layout.addWidget(self.auto_refresh_label)
        header_layout.addWidget(self.state_label)

        self.results_root_label = QLabel("No GOW results directory selected")
        self.results_root_label.setObjectName("resultsRoot")
        self.results_root_label.setMaximumHeight(18)
        self.results_root_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.stack = QStackedWidget()

        self.overview_page = OverviewPage()
        self.page_titles["Overview"] = (
            self.overview_page.title_label
        )

        self.overview_scroll = QScrollArea()
        self.overview_scroll.setObjectName("overviewScroll")
        self.overview_scroll.setWidgetResizable(True)
        self.overview_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )
        self.overview_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.overview_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.overview_scroll.setWidget(self.overview_page)
        self.overview_scroll.viewport().setObjectName(
            "overviewScrollViewport"
        )

        self.stack.addWidget(self.overview_scroll)
        for key, title in NAVIGATION_ITEMS:
            if key == "Overview":
                continue
            self.stack.addWidget(self._create_placeholder_page(title, key))

        layout.addWidget(header)
        layout.addWidget(self.results_root_label)
        layout.addWidget(self.stack, 1)
        return content

    def _create_placeholder_page(self, title: str, key: str) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        self.page_titles[key] = title_label

        description = QLabel(
            "Independent desktop monitoring framework. "
            "The application reads GOW artifacts through filesystem adapters "
            "and does not import GOW internals."
        )
        description.setObjectName("description")
        description.setWordWrap(True)

        panel = QFrame()
        panel.setObjectName("emptyPanel")
        panel_layout = QVBoxLayout(panel)

        placeholder = QLabel("No GOW run connected")
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        self.placeholder_labels[key] = placeholder
        panel_layout.addWidget(placeholder)

        layout.addWidget(title_label)
        layout.addWidget(description)
        layout.addWidget(panel, 1)
        return page

    def select_page(self, key: str) -> None:
        keys = [item[0] for item in NAVIGATION_ITEMS]
        if key not in keys:
            raise KeyError(f"Unknown monitor page: {key}")

        self.stack.setCurrentIndex(keys.index(key))
        for button_key, button in self.navigation_buttons.items():
            button.setChecked(button_key == key)

    def connect_results_root(self, results_root: str | Path) -> None:
        reader, snapshots, histories = self._load_monitor_data(results_root)

        self._connected_path = reader.selected_path
        self._apply_monitor_data(
            reader,
            snapshots,
            histories,
            preferred_run_id=None,
        )
        self.live_refresh.connect_path(reader.selected_path)
        self._set_refresh_status(
            "AUTO 1s",
            "live",
            "GOW artifacts are refreshed every second in a background worker.",
        )

    def refresh_connected_results(self) -> bool:
        """Request an immediate refresh without changing the selected folder."""

        return self.live_refresh.refresh_now()

    @staticmethod
    def _load_monitor_data(
        results_root: str | Path,
    ) -> tuple[
        GowFilesystemRunReader,
        tuple[RunSnapshot, ...],
        dict[str, tuple[EvaluationPoint, ...]],
    ]:
        reader = GowFilesystemRunReader(results_root)
        snapshots: list[RunSnapshot] = []
        histories: dict[str, tuple[EvaluationPoint, ...]] = {}

        for reference in reader.discover_runs():
            snapshot, history = reader.snapshot_and_history_of(reference)
            snapshots.append(snapshot)
            histories[reference.run_id] = history

        return reader, tuple(snapshots), histories

    def _apply_monitor_data(
        self,
        reader: GowFilesystemRunReader,
        snapshots: tuple[RunSnapshot, ...],
        histories: dict[str, tuple[EvaluationPoint, ...]],
        *,
        preferred_run_id: str | None,
    ) -> None:
        self._reader = reader
        self._snapshots = snapshots
        self._histories = histories
        self.results_root_label.setText(str(reader.results_root))
        self.results_root_label.setToolTip(str(reader.selected_path))

        selected_index = 0
        self.run_selector.blockSignals(True)
        self.run_selector.clear()
        for index, snapshot in enumerate(snapshots):
            reference = snapshot.reference
            problem = reference.problem_id or "unknown problem"
            self.run_selector.addItem(
                f"{reference.run_id} | {problem}",
                reference.run_id,
            )
            if reference.run_id == preferred_run_id:
                selected_index = index
        self.run_selector.blockSignals(False)
        self.run_selector.setEnabled(bool(snapshots))

        if snapshots:
            self.run_selector.setCurrentIndex(selected_index)
            self._render_snapshot(snapshots[selected_index])
        else:
            self._render_no_run(
                "No runs found yet. Auto-refresh is watching the selected "
                "directory for new GOW artifacts."
            )

    def _choose_results_root(self) -> None:
        initial = (
            str(self._reader.selected_path)
            if self._reader is not None
            else str(Path.home())
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select GOW results directory",
            initial,
        )
        if not selected:
            return
        try:
            self.connect_results_root(selected)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Unable to read GOW results",
                str(exc),
            )

    def _selected_run_changed(self, index: int) -> None:
        if 0 <= index < len(self._snapshots):
            self._render_snapshot(self._snapshots[index])

    def _refresh_started(self) -> None:
        self._set_refresh_status(
            "SYNC",
            "busy",
            "Reading new GOW artifacts outside the UI thread.",
        )

    def _refresh_completed(self, payload: object) -> None:
        if not isinstance(payload, LiveRefreshPayload):
            return
        if self._connected_path is None:
            return
        if payload.selected_path != self._connected_path:
            return

        preferred_run_id = self.run_selector.currentData()
        if not isinstance(preferred_run_id, str):
            preferred_run_id = None

        monitor_data_changed = (
            payload.snapshots != self._snapshots
            or payload.histories != self._histories
        )
        if monitor_data_changed:
            self._apply_monitor_data(
                payload.reader,
                payload.snapshots,
                payload.histories,
                preferred_run_id=preferred_run_id,
            )
        else:
            self._reader = payload.reader

        self._set_refresh_status(
            "AUTO 1s",
            "live",
            "Live refresh is active. The selected run is preserved.",
        )

    def _refresh_failed(self, message: str) -> None:
        self._set_refresh_status(
            "AUTO ERR",
            "error",
            message or "Unable to refresh GOW artifacts.",
        )

    def _render_snapshot(self, snapshot: RunSnapshot) -> None:
        reference = snapshot.reference
        self.job_label.setText(f"Job: {reference.run_id}")
        self._set_state(snapshot.state)

        self.sidebar_run_id.setText(f"Run: {reference.run_id}")
        self.sidebar_problem.setText(
            f"Problem: {reference.problem_id or 'unknown'}"
        )
        if snapshot.planned_evaluations is None:
            evaluations_text = f"{snapshot.evaluation_count:,}"
        else:
            evaluations_text = (
                f"{snapshot.evaluation_count:,} / "
                f"{snapshot.planned_evaluations:,}"
            )
        self.sidebar_evaluations.setText(
            f"Evaluations: {evaluations_text}"
        )
        self.sidebar_failures.setText(
            f"Failures: {snapshot.failed_evaluations}"
        )

        history = self._histories.get(reference.run_id, ())
        self.overview_page.render_snapshot(snapshot, history)

        for key in self.placeholder_labels:
            self.placeholder_labels[key].setText(
                f"{reference.run_id} connected.\n"
                f"The {key} view will use this run."
            )

    def _render_no_run(self, message: str = "No GOW run connected") -> None:
        self.job_label.setText("Job: No run selected")
        self._set_state(RunState.UNKNOWN)
        self.sidebar_run_id.setText("Run: -")
        self.sidebar_problem.setText("Problem: -")
        self.sidebar_evaluations.setText("Evaluations: 0")
        self.sidebar_failures.setText("Failures: 0")
        self._histories = {}
        self.overview_page.clear(message)
        for label in self.placeholder_labels.values():
            label.setText(message)

    def _set_state(self, state: RunState) -> None:
        self.state_label.setText(state.value.upper())
        self.state_label.setProperty("runState", state.value)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def _set_refresh_status(
        self,
        text: str,
        state: str,
        tooltip: str,
    ) -> None:
        self.auto_refresh_label.setText(text)
        self.auto_refresh_label.setProperty("refreshState", state)
        self.auto_refresh_label.setToolTip(tooltip)
        self.auto_refresh_label.style().unpolish(self.auto_refresh_label)
        self.auto_refresh_label.style().polish(self.auto_refresh_label)

    def _resource_sampled(self, payload: object) -> None:
        if not isinstance(payload, SystemResourceSnapshot):
            return

        self._resource_history.append(payload)
        self.overview_page.render_resource_snapshot(
            payload,
            tuple(self._resource_history),
        )

    def _resource_failed(self, message: str) -> None:
        self.overview_page.render_resource_error(
            message or "Host telemetry is temporarily unavailable"
        )

    def _gow_resource_sampled(self, payload: object) -> None:
        if not isinstance(payload, GowProcessResourceSnapshot):
            return

        self._gow_resource_history.append(payload)
        self.overview_page.render_gow_resource_snapshot(
            payload,
            tuple(self._gow_resource_history),
        )

    def _gow_resource_failed(self, message: str) -> None:
        self.overview_page.render_gow_resource_error(
            message or "GOW process telemetry is temporarily unavailable"
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self.resource_monitor.is_active:
            self.resource_monitor.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.live_refresh.stop()
        self.resource_monitor.stop()
        super().closeEvent(event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#content, QWidget#page,
            QScrollArea#overviewScroll,
            QWidget#overviewScrollViewport {
                background: #080E17;
                color: #DCE6F2;
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QFrame#sidebar {
                background: #0A1320;
                border-right: 1px solid #1F3044;
            }
            QLabel#brand {
                color: #E7EEF7;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#brandSubtitle, QLabel#sidebarFooter,
            QLabel#description, QLabel#resultsRoot, QLabel#sidebarInfo {
                color: #7F91A8;
            }
            QLabel#sidebarSectionTitle {
                color: #DCE6F2;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#navigationButton {
                background: transparent;
                color: #8FA2B8;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 10px 12px;
                text-align: left;
            }
            QPushButton#navigationButton:hover {
                background: #101E2E;
                color: #DCE6F2;
            }
            QPushButton#navigationButton:checked {
                background: #10243A;
                color: #59B6FF;
                border-color: #1D5278;
            }
            QFrame#header, QFrame#emptyPanel {
                background: #0D1623;
                border: 1px solid #1F3044;
                border-radius: 6px;
            }
            QLabel#jobTitle {
                font-size: 16px;
                font-weight: 600;
            }
            QLabel#stateBadge, QLabel#refreshBadge {
                background: #1A2736;
                color: #9FB1C5;
                border: 1px solid #33465C;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#stateBadge[runState="running"] {
                background: #173B2B;
                color: #72E2A7;
                border-color: #245C42;
            }
            QLabel#stateBadge[runState="completed"] {
                background: #163548;
                color: #67D7FF;
                border-color: #225873;
            }
            QLabel#stateBadge[runState="waiting"] {
                background: #41361A;
                color: #F6CE66;
                border-color: #675525;
            }
            QLabel#stateBadge[runState="failed"] {
                background: #421E25;
                color: #FF7A86;
                border-color: #6E2C37;
            }
            QLabel#refreshBadge[refreshState="live"] {
                background: #173B2B;
                color: #72E2A7;
                border-color: #245C42;
            }
            QLabel#refreshBadge[refreshState="busy"] {
                background: #163548;
                color: #67D7FF;
                border-color: #225873;
            }
            QLabel#refreshBadge[refreshState="error"] {
                background: #421E25;
                color: #FF7A86;
                border-color: #6E2C37;
            }
            QFrame#kpiCard {
                background: #0D1623;
                border: 1px solid #1F3044;
                border-radius: 6px;
            }
            QFrame#kpiCard[kpiTone="good"] {
                border-color: #245C42;
            }
            QFrame#kpiCard[kpiTone="warning"] {
                border-color: #675525;
            }
            QFrame#kpiCard[kpiTone="bad"] {
                border-color: #6E2C37;
            }
            QFrame#kpiCard[kpiVisual="gauge"] {
                background: #0C1724;
            }
            QLabel#kpiTitle {
                color: #7F91A8;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#kpiValue {
                color: #E7EEF7;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#kpiDetail {
                color: #7890A9;
                font-size: 11px;
            }
            QFrame#dashboardPanel, QFrame#runHealthPanel,
            QFrame#metricPanel {
                background: #0D1623;
                border: 1px solid #1F3044;
                border-radius: 6px;
            }
            QFrame#metricTile {
                background: #0A121E;
                border: 1px solid #1A2A3D;
                border-radius: 4px;
            }
            QFrame#metricTile[metricTone="good"] {
                border-bottom: 2px solid #3DBA77;
            }
            QFrame#metricTile[metricTone="warning"] {
                border-bottom: 2px solid #E0B94E;
            }
            QFrame#metricTile[metricTone="bad"] {
                border-bottom: 2px solid #F05B68;
            }
            QLabel#metricTitle {
                color: #7890A9;
                font-size: 10px;
                font-weight: 600;
            }
            QLabel#metricValue {
                color: #E7EEF7;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#metricDetail {
                color: #71869E;
                font-size: 10px;
            }
            QLabel#availabilityBadge {
                color: #72E2A7;
                background: #173B2B;
                border: 1px solid #245C42;
                border-radius: 3px;
                padding: 2px 5px;
                font-size: 9px;
                font-weight: 700;
            }
            QLabel#panelTitle {
                color: #DCE6F2;
                font-size: 13px;
                font-weight: 700;
            }
            QFrame#chartMetaBar {
                background: #09111C;
                border-top: 1px solid #1A2A3D;
                border-radius: 3px;
            }
            QLabel#chartFooter {
                color: #71869E;
                font-family: "Consolas";
                font-size: 10px;
            }
            QFrame#healthRow {
                background: #0A121E;
                border: 1px solid #1A2A3D;
                border-radius: 4px;
            }
            QFrame#healthRow[severity="good"] {
                border-left: 3px solid #3DBA77;
            }
            QFrame#healthRow[severity="warning"] {
                border-left: 3px solid #E0B94E;
            }
            QFrame#healthRow[severity="critical"] {
                border-left: 3px solid #F05B68;
            }
            QLabel#healthTitle {
                color: #DCE6F2;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#healthDetail {
                color: #7890A9;
                font-size: 11px;
            }
            QLabel#healthSeverity, QLabel#healthSummary {
                color: #8FA2B8;
                border: 1px solid #33465C;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                font-weight: 700;
            }
            QFrame#healthRow[severity="good"] QLabel#healthSeverity,
            QLabel#healthSummary[healthState="healthy"] {
                color: #72E2A7;
                border-color: #245C42;
                background: #173B2B;
            }
            QFrame#healthRow[severity="warning"] QLabel#healthSeverity,
            QLabel#healthSummary[healthState="attention"] {
                color: #F6CE66;
                border-color: #675525;
                background: #41361A;
            }
            QFrame#healthRow[severity="critical"] QLabel#healthSeverity {
                color: #FF7A86;
                border-color: #6E2C37;
                background: #421E25;
            }
            QLabel#pageTitle {
                color: #E7EEF7;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#placeholder {
                color: #7890A9;
                font-size: 16px;
            }
            QComboBox#runSelector {
                background: #09111C;
                color: #DCE6F2;
                border: 1px solid #2A3C51;
                border-radius: 4px;
                padding: 7px 10px;
            }
            QComboBox#windowSelector {
                background: #09111C;
                color: #B9C8D8;
                border: 1px solid #2A3C51;
                border-radius: 4px;
                padding: 5px 8px;
                min-width: 130px;
            }
            QPushButton#primaryButton {
                background: #1769AA;
                color: #F4F8FC;
                border: 1px solid #2B83C6;
                border-radius: 4px;
                padding: 7px 12px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: #1E7BC1;
            }
            """
        )
