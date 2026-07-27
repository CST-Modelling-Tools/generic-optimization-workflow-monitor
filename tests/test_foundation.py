from pathlib import Path

import pytest

from gow_monitor.domain import ObjectiveDirection, RunReference
from gow_monitor.ui.main_window import MainWindow


def test_run_reference_is_independent_domain_model() -> None:
    run = RunReference(
        run_id="run-001",
        run_root=Path("results/runs/run-001"),
        direction=ObjectiveDirection.MINIMIZE,
    )

    assert run.run_id == "run-001"
    assert run.direction is ObjectiveDirection.MINIMIZE
    assert run.run_root == Path("results/runs/run-001")


def test_run_reference_rejects_empty_identifier() -> None:
    with pytest.raises(ValueError, match="run_id cannot be empty"):
        RunReference(
            run_id=" ",
            run_root=Path("results"),
            direction=ObjectiveDirection.MINIMIZE,
        )


def test_desktop_shell_contains_required_navigation(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "GOW Monitor"
    assert tuple(window.navigation_buttons) == (
        "Overview",
        "Progress",
        "Search Behavior",
        "Resources",
        "Alerts",
        "Provenance",
        "Configuration",
    )

    window.select_page("Alerts")
    assert window.navigation_buttons["Alerts"].isChecked()
    assert window.stack.currentIndex() == 4
