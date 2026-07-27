from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

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

        self.setWindowTitle("GOW Monitor")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 650)

        self._build_ui()
        self._apply_style()
        self.select_page("Overview")

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

        brand = QLabel("?  GOW")
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

        version = QLabel("Framework foundation ? v0.1.0")
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

        job_label = QLabel("Job: No run selected")
        job_label.setObjectName("jobTitle")

        state_label = QLabel("IDLE")
        state_label.setObjectName("stateBadge")
        state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state_label.setFixedWidth(76)

        header_layout.addWidget(job_label)
        header_layout.addStretch(1)
        header_layout.addWidget(state_label)

        self.stack = QStackedWidget()

        for key, title in NAVIGATION_ITEMS:
            page = self._create_placeholder_page(title)
            self.stack.addWidget(page)
            self.page_titles[key] = page.findChild(QLabel, "pageTitle")

        layout.addWidget(header)
        layout.addWidget(self.stack, 1)

        return content

    @staticmethod
    def _create_placeholder_page(title: str) -> QWidget:
        page = QWidget()
        page.setObjectName("page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")

        description = QLabel(
            "Independent desktop framework foundation. "
            "GOW run discovery and live telemetry will be connected "
            "through infrastructure adapters."
        )
        description.setObjectName("description")
        description.setWordWrap(True)

        panel = QFrame()
        panel.setObjectName("emptyPanel")
        panel_layout = QVBoxLayout(panel)

        placeholder = QLabel("No GOW run connected")
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        panel_layout.addWidget(placeholder)

        layout.addWidget(title_label)
        layout.addWidget(description)
        layout.addWidget(panel, 1)

        return page

    def select_page(self, key: str) -> None:
        keys = [item[0] for item in NAVIGATION_ITEMS]

        if key not in keys:
            raise KeyError(f"Unknown monitor page: {key}")

        index = keys.index(key)
        self.stack.setCurrentIndex(index)

        for button_key, button in self.navigation_buttons.items():
            button.setChecked(button_key == key)

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

            QLabel#brandSubtitle,
            QLabel#sidebarFooter,
            QLabel#description {
                color: #7F91A8;
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

            QFrame#header,
            QFrame#emptyPanel {
                background: #0D1623;
                border: 1px solid #1F3044;
                border-radius: 6px;
            }

            QLabel#jobTitle {
                font-size: 16px;
                font-weight: 600;
            }

            QLabel#stateBadge {
                background: #173B2B;
                color: #72E2A7;
                border: 1px solid #245C42;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#pageTitle {
                color: #E7EEF7;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#placeholder {
                color: #60748C;
                font-size: 18px;
            }
            """
        )
