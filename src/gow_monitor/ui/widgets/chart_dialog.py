from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChartDialog(QDialog):
    # Large non-modal chart window with navigation help.

    def __init__(
        self,
        title: str,
        chart: QWidget,
        *,
        footer_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chart = chart

        self.setObjectName("chartDialog")
        self.setWindowTitle(f"GOW Monitor - {title}")
        self.setModal(False)
        self.resize(1220, 760)
        self.setMinimumSize(900, 560)
        self.setWindowFlag(Qt.WindowType.Window, True)

        owner = parent.window() if parent is not None else None
        if owner is not None and owner.styleSheet():
            self.setStyleSheet(owner.styleSheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("chartDialogHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 8, 8)
        header_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("chartDialogTitle")

        zoom_in_button = QPushButton("Zoom +")
        zoom_in_button.setObjectName("chartActionButton")
        zoom_in_button.clicked.connect(self._zoom_in)

        zoom_out_button = QPushButton("Zoom -")
        zoom_out_button.setObjectName("chartActionButton")
        zoom_out_button.clicked.connect(self._zoom_out)

        reset_button = QPushButton("Reset view")
        reset_button.setObjectName("chartActionButton")
        reset_button.clicked.connect(self._reset_view)

        close_button = QPushButton("Close")
        close_button.setObjectName("chartActionButton")
        close_button.clicked.connect(self.close)

        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(zoom_in_button)
        header_layout.addWidget(zoom_out_button)
        header_layout.addWidget(reset_button)
        header_layout.addWidget(close_button)

        chart.setMinimumHeight(460)

        footer = QFrame()
        footer.setObjectName("chartDialogFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(3)

        self.footer_label = QLabel(footer_text)
        self.footer_label.setObjectName("chartDialogFooterText")
        self.footer_label.setWordWrap(True)

        controls = QLabel(
            "Navigation: click point = inspect value  |  "
            "wheel or Zoom +/- = zoom  |  left-drag = pan  |  "
            "double-click or Reset view = full range"
        )
        controls.setObjectName("chartDialogControls")
        controls.setWordWrap(True)

        footer_layout.addWidget(self.footer_label)
        footer_layout.addWidget(controls)

        layout.addWidget(header)
        layout.addWidget(chart, 1)
        layout.addWidget(footer)

    def _zoom_in(self, checked: bool = False) -> None:
        del checked
        zoom = getattr(self.chart, "zoom_in", None)
        if callable(zoom):
            zoom()

    def _zoom_out(self, checked: bool = False) -> None:
        del checked
        zoom = getattr(self.chart, "zoom_out", None)
        if callable(zoom):
            zoom()

    def _reset_view(self, checked: bool = False) -> None:
        del checked
        reset = getattr(self.chart, "reset_view", None)
        if callable(reset):
            reset()

    def present(self) -> None:
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
