from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from gow_monitor import __version__
from gow_monitor.ui.main_window import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gow-monitor",
        description="Independent desktop monitor for GOW runs.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)

    application = QApplication.instance()
    owns_application = application is None

    if application is None:
        application = QApplication(sys.argv[:1])

    application.setApplicationName("GOW Monitor")
    application.setOrganizationName("CST Modelling Tools")
    application.setStyle("Fusion")

    window = MainWindow()
    window.show()

    if not owns_application:
        return 0

    return int(application.exec())
