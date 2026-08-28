from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)


class Header(QFrame):
    """Reusable top bar for run selection and monitor status."""

    run_selected = Signal(int)
    open_results_clicked = Signal()
    pause_clicked = Signal()
    continue_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(10)

        self.job_label = QLabel("Job: No run selected")
        self.job_label.setObjectName("jobTitle")

        self.run_selector = QComboBox()
        self.run_selector.setObjectName("runSelector")
        self.run_selector.setMinimumWidth(220)
        self.run_selector.setEnabled(False)
        self.run_selector.currentIndexChanged.connect(
            self.run_selected.emit
        )

        self.open_results_button = QPushButton("Open GOW results")
        self.open_results_button.setObjectName("primaryButton")
        self.open_results_button.clicked.connect(
            self._emit_open_results
        )

        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("primaryButton")
        self.pause_button.setEnabled(False)
        self.pause_button.setToolTip(
            "Request a cooperative pause at the next safe "
            "completed-generation boundary."
        )
        self.pause_button.clicked.connect(
            self._emit_pause
        )

        self.continue_button = QPushButton("Continue")
        self.continue_button.setObjectName("primaryButton")
        self.continue_button.setEnabled(False)
        self.continue_button.setToolTip(
            "Resume this paused GOW run from its persisted checkpoint."
        )
        self.continue_button.clicked.connect(
            self._emit_continue
        )

        self.auto_refresh_label = QLabel("AUTO OFF")
        self.auto_refresh_label.setObjectName("refreshBadge")
        self.auto_refresh_label.setProperty("refreshState", "off")
        self.auto_refresh_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.auto_refresh_label.setMinimumWidth(82)

        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("stateBadge")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumWidth(92)

        layout.addWidget(self.job_label)
        layout.addStretch(1)
        layout.addWidget(self.run_selector)
        layout.addWidget(self.open_results_button)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.continue_button)
        layout.addWidget(self.auto_refresh_label)
        layout.addWidget(self.state_label)

    def _emit_open_results(self, checked: bool = False) -> None:
        del checked
        self.open_results_clicked.emit()

    def _emit_pause(self, checked: bool = False) -> None:
        del checked
        self.pause_clicked.emit()

    def _emit_continue(self, checked: bool = False) -> None:
        del checked
        self.continue_clicked.emit()

    def populate_runs(
        self,
        snapshots,
        selected_index: int = 0,
    ) -> None:
        self.run_selector.blockSignals(True)
        self.run_selector.clear()

        for snapshot in snapshots:
            reference = snapshot.reference
            problem = reference.problem_id or "unknown problem"
            self.run_selector.addItem(
                f"{reference.run_id} | {problem}",
                reference.run_id,
            )

        self.run_selector.blockSignals(False)
        self.run_selector.setEnabled(bool(snapshots))

        if snapshots:
            self.run_selector.setCurrentIndex(selected_index)

    def clear_runs(self) -> None:
        self.run_selector.blockSignals(True)
        self.run_selector.clear()
        self.run_selector.blockSignals(False)
        self.run_selector.setEnabled(False)

    def set_job_title(self, text: str) -> None:
        self.job_label.setText(text)

    def set_refresh_status(
        self,
        text: str,
        state: str,
        tooltip: str,
    ) -> None:
        self.auto_refresh_label.setText(text)
        self.auto_refresh_label.setProperty("refreshState", state)
        self.auto_refresh_label.setToolTip(tooltip)
        self.auto_refresh_label.style().unpolish(
            self.auto_refresh_label
        )
        self.auto_refresh_label.style().polish(
            self.auto_refresh_label
        )

    def set_run_state(self, state) -> None:
        self.state_label.setText(state.value.upper())
        self.state_label.setProperty("runState", state.value)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

        self.pause_button.setEnabled(
            state.value == "running"
        )

        self.continue_button.setEnabled(
            state.value == "paused"
        )

    def current_run_id(self) -> str | None:
        data = self.run_selector.currentData()
        return data if isinstance(data, str) else None
