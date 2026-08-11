from __future__ import annotations

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

NAVIGATION_ITEMS = (
    ("Overview", "Overview"),
    ("Progress", "Optimization Progress"),
    ("Search Behavior", "Search Behavior"),
    ("Resources", "Resources Utilization"),
    ("Alerts", "Run Alerts"),
    ("Provenance", "Run Provenance"),
    ("Configuration", "Configuration"),
)


class Sidebar(QFrame):
    """Reusable navigation and run-information sidebar."""

    page_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(210)

        self.navigation_buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(8)

        self.brand_label = QLabel("GOW")
        self.brand_label.setObjectName("brand")

        subtitle = QLabel("Optimization Monitor")
        subtitle.setObjectName("brandSubtitle")

        layout.addWidget(self.brand_label)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        for key, _title in NAVIGATION_ITEMS:
            button = QPushButton(key)
            button.setObjectName("navigationButton")
            button.setCheckable(True)
            button.clicked.connect(
                partial(self._navigation_clicked, key)
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
        self.version_label.setObjectName("sidebarFooter")
        self.version_label.setWordWrap(True)
        layout.addWidget(self.version_label)

    def _navigation_clicked(
        self,
        key: str,
        checked: bool = False,
    ) -> None:
        del checked
        self.page_selected.emit(key)

    def set_run_info(
        self,
        run_id: str,
        problem: str,
        evaluations: str,
        failures: str,
    ) -> None:
        self.sidebar_run_id.setText(f"Run: {run_id}")
        self.sidebar_problem.setText(f"Problem: {problem}")
        self.sidebar_evaluations.setText(
            f"Evaluations: {evaluations}"
        )
        self.sidebar_failures.setText(f"Failures: {failures}")

    def clear_info(self) -> None:
        self.sidebar_run_id.setText("Run: -")
        self.sidebar_problem.setText("Problem: -")
        self.sidebar_evaluations.setText("Evaluations: 0")
        self.sidebar_failures.setText("Failures: 0")

    def set_active_page(self, key: str) -> None:
        for button_key, button in self.navigation_buttons.items():
            button.setChecked(button_key == key)
