from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gow_monitor.domain import RunSnapshot, RunState
from gow_monitor.infrastructure import GowFilesystemRunReader

NAVIGATION_ITEMS = (
    ("Overview", "Overview"),
    ("Progress", "Optimization Progress"),
    ("Search Behavior", "Search Behavior"),
    ("Resources", "Resources Utilization"),
    ("Alerts", "Run Alerts"),
    ("Provenance", "Run Provenance"),
    ("Configuration", "Configuration"),
)


class MainWindow(QMainWindow):
    """Top-level desktop shell for the independent monitor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.navigation_buttons: dict[str, QPushButton] = {}
        self.page_titles: dict[str, QLabel] = {}
        self.placeholder_labels: dict[str, QLabel] = {}
        self._reader: GowFilesystemRunReader | None = None
        self._snapshots: tuple[RunSnapshot, ...] = ()

        self.setWindowTitle("GOW Monitor")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 650)

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

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(8)

        brand = QLabel("◉  GOW")
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

        self.sidebar_run_id = QLabel("Run: —")
        self.sidebar_problem = QLabel("Problem: —")
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
        version = QLabel("Framework foundation · v0.1.0")
        version.setObjectName("sidebarFooter")
        version.setWordWrap(True)
        layout.addWidget(version)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        self.job_label = QLabel("Job: No run selected")
        self.job_label.setObjectName("jobTitle")

        self.run_selector = QComboBox()
        self.run_selector.setObjectName("runSelector")
        self.run_selector.setMinimumWidth(240)
        self.run_selector.setEnabled(False)
        self.run_selector.currentIndexChanged.connect(self._selected_run_changed)

        self.open_results_button = QPushButton("Open GOW results")
        self.open_results_button.setObjectName("primaryButton")
        self.open_results_button.clicked.connect(self._choose_results_root)

        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("stateBadge")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumWidth(92)

        header_layout.addWidget(self.job_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.run_selector)
        header_layout.addWidget(self.open_results_button)
        header_layout.addWidget(self.state_label)

        self.results_root_label = QLabel("No GOW results directory selected")
        self.results_root_label.setObjectName("resultsRoot")
        self.results_root_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.stack = QStackedWidget()
        for key, title in NAVIGATION_ITEMS:
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
        reader = GowFilesystemRunReader(results_root)
        snapshots = tuple(
            reader.snapshot_of(reference)
            for reference in reader.discover_runs()
        )

        self._reader = reader
        self._snapshots = snapshots
        self.results_root_label.setText(str(reader.results_root))
        self.results_root_label.setToolTip(str(reader.results_root))

        self.run_selector.blockSignals(True)
        self.run_selector.clear()
        for snapshot in snapshots:
            reference = snapshot.reference
            problem = reference.problem_id or "unknown problem"
            self.run_selector.addItem(
                f"{reference.run_id} · {problem}",
                reference.run_id,
            )
        self.run_selector.blockSignals(False)
        self.run_selector.setEnabled(bool(snapshots))

        if snapshots:
            self.run_selector.setCurrentIndex(0)
            self._render_snapshot(snapshots[0])
        else:
            self._render_no_run(
                "No runs found. Select a GOW results directory containing "
                "a runs/ subdirectory."
            )

    def _choose_results_root(self) -> None:
        initial = (
            str(self._reader.results_root)
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

    def _render_snapshot(self, snapshot: RunSnapshot) -> None:
        reference = snapshot.reference
        self.job_label.setText(f"Job: {reference.run_id}")
        self._set_state(snapshot.state)

        self.sidebar_run_id.setText(f"Run: {reference.run_id}")
        self.sidebar_problem.setText(
            f"Problem: {reference.problem_id or 'unknown'}"
        )
        self.sidebar_evaluations.setText(
            f"Evaluations: {snapshot.evaluation_count}"
        )
        self.sidebar_failures.setText(
            f"Failures: {snapshot.failed_evaluations}"
        )

        self.placeholder_labels["Overview"].setText(
            f"Run connected\n\n"
            f"Run ID: {reference.run_id}\n"
            f"Problem: {reference.problem_id or 'unknown'}\n"
            f"Direction: {reference.direction.value}\n"
            f"State: {snapshot.state.value}\n"
            f"Evaluations found: {snapshot.evaluation_count}\n"
            f"Failed evaluations: {snapshot.failed_evaluations}\n\n"
            f"{reference.run_root}"
        )

        for key in self.placeholder_labels:
            if key != "Overview":
                self.placeholder_labels[key].setText(
                    f"{reference.run_id} connected.\n"
                    f"The {key} view will use this run."
                )

    def _render_no_run(self, message: str = "No GOW run connected") -> None:
        self.job_label.setText("Job: No run selected")
        self._set_state(RunState.UNKNOWN)
        self.sidebar_run_id.setText("Run: —")
        self.sidebar_problem.setText("Problem: —")
        self.sidebar_evaluations.setText("Evaluations: 0")
        self.sidebar_failures.setText("Failures: 0")
        for label in self.placeholder_labels.values():
            label.setText(message)

    def _set_state(self, state: RunState) -> None:
        self.state_label.setText(state.value.upper())
        self.state_label.setProperty("runState", state.value)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#content, QWidget#page {
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
            QLabel#stateBadge {
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
            QLabel#pageTitle {
                color: #E7EEF7;
                font-size: 22px;
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
