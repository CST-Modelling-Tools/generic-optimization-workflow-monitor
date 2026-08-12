from __future__ import annotations

from pathlib import Path

from gow_monitor.domain import (
    ObjectiveDirection,
    RunReference,
    RunSnapshot,
    RunState,
)
from gow_monitor.ui.pages.overview_page import OverviewPage


def _snapshot(
    *,
    best: float = 8.780611487770038,
    state: RunState = RunState.RUNNING,
    started_at: float = 100.0,
    finished_at: float | None = None,
) -> RunSnapshot:
    return RunSnapshot(
        reference=RunReference(
            run_id="precision-timer-test",
            run_root=Path("."),
            direction=ObjectiveDirection.MINIMIZE,
            problem_id="test",
        ),
        state=state,
        evaluation_count=10,
        failed_evaluations=0,
        result_sources=1,
        successful_evaluations=10,
        best_objective=best,
        run_started_at=started_at,
        run_finished_at=finished_at,
    )


def test_objective_defaults_to_two_decimals_and_can_increase(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page.render_snapshot(_snapshot())

    assert page._objective_decimals == 2
    assert page.cards["best"].value_label.text() == "8.78"
    assert not page.cards["best"].decrease_button.isEnabled()
    assert page.cards["best"].increase_button.isEnabled()

    page.cards["best"].increase_button.click()

    assert page._objective_decimals == 3
    assert page.cards["best"].value_label.text() == "8.781"
    assert page.cards["best"].decrease_button.isEnabled()


def test_objective_precision_is_bounded_between_two_and_twelve(
    qtbot,
) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page.render_snapshot(_snapshot())

    page._set_objective_decimals(50)

    assert page._objective_decimals == 12
    assert page.cards["best"].value_label.text() == "8.780611487770"
    assert not page.cards["best"].increase_button.isEnabled()

    page._set_objective_decimals(-50)

    assert page._objective_decimals == 2
    assert page.cards["best"].value_label.text() == "8.78"
    assert not page.cards["best"].decrease_button.isEnabled()


def test_center_timer_shows_final_duration(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)

    page.render_snapshot(
        _snapshot(
            state=RunState.COMPLETED,
            started_at=100.0,
            finished_at=161.0,
        )
    )

    assert page.timer_value_label.text() == "00:01:01"
    assert page.timer_status_label.text() == "FINAL"
    assert page.timer_panel.property("timerState") == "final"
