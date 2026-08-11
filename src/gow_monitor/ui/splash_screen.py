from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class SplashScreen(QWidget):
    # Animated startup screen shown before the main monitor window.

    def __init__(self) -> None:
        super().__init__(None)

        self.setObjectName("startupSplash")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 270)

        self._target_window: QWidget | None = None
        self._progress_value = 8
        self._dot_index = 0

        self._elapsed = QElapsedTimer()
        self._elapsed.start()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(45)
        self._pulse_timer.timeout.connect(self._advance_animation)

        self._fade_animation = QPropertyAnimation(
            self,
            b"windowOpacity",
            self,
        )
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self._fade_animation.finished.connect(
            self._reveal_target
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 36, 42, 32)
        layout.setSpacing(9)

        brand = QLabel("GOW")
        brand.setObjectName("splashBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        product = QLabel("GENERIC OPTIMIZATION WORKFLOW")
        product.setObjectName("splashProduct")
        product.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Optimization Monitor")
        subtitle.setObjectName("splashSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(brand)
        layout.addWidget(product)
        layout.addWidget(subtitle)
        layout.addStretch(1)

        self.status_label = QLabel("Preparing monitor")
        self.status_label.setObjectName("splashStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("splashProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(self._progress_value)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        self.setStyleSheet(
            '''
            QWidget#startupSplash {
                background: #080E17;
                border: 1px solid #2A4058;
                border-radius: 14px;
            }
            QLabel#splashBrand {
                color: #EAF4FF;
                font-family: "Segoe UI";
                font-size: 54px;
                font-weight: 800;
                letter-spacing: 7px;
            }
            QLabel#splashProduct {
                color: #59B6FF;
                font-family: "Segoe UI";
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#splashSubtitle {
                color: #8396AC;
                font-family: "Segoe UI";
                font-size: 14px;
            }
            QLabel#splashStatus {
                color: #71869E;
                font-family: "Segoe UI";
                font-size: 10px;
            }
            QProgressBar#splashProgress {
                background: #101E2E;
                border: 0;
                border-radius: 2px;
            }
            QProgressBar#splashProgress::chunk {
                background: #2F8DD3;
                border-radius: 2px;
            }
            '''
        )

        self._center_on_screen()
        self._pulse_timer.start()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        area = screen.availableGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.center().y() - self.height() // 2,
        )

    def _advance_animation(self) -> None:
        if self._progress_value < 92:
            self._progress_value += 2
            self.progress_bar.setValue(self._progress_value)

        dots = "." * self._dot_index
        self.status_label.setText(f"Preparing monitor{dots}")
        self._dot_index = (self._dot_index + 1) % 4

    def finish(
        self,
        target_window: QWidget,
        *,
        minimum_ms: int = 1050,
    ) -> None:
        self._target_window = target_window
        remaining = max(0, minimum_ms - self._elapsed.elapsed())
        QTimer.singleShot(remaining, self._begin_fade)

    def _begin_fade(self) -> None:
        self._pulse_timer.stop()
        self.progress_bar.setValue(100)
        self.status_label.setText("Ready")
        self._fade_animation.start()

    def _reveal_target(self) -> None:
        target = self._target_window
        self.close()
        if target is None:
            return

        target.show()
        target.raise_()
        target.activateWindow()
