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



def test_timer_freezes_while_paused_and_continues_without_jump(
    qtbot,
    monkeypatch,
) -> None:
    now = [130.0]

    monkeypatch.setattr(
        "gow_monitor.ui.pages.overview_page.time.time",
        lambda: now[0],
    )

    page = OverviewPage()
    qtbot.addWidget(page)

    # Avoid a real Qt tick interfering with the deterministic fake clock.
    page.runtime_timer.stop()

    # 30 seconds of active execution.
    page.render_snapshot(
        _snapshot(
            state=RunState.RUNNING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:30"
    assert page.timer_status_label.text() == "LIVE"

    # PAUSE_REQUESTED is still active work: GOW may be finishing a safe
    # generation boundary.
    now[0] = 135.0

    page.render_snapshot(
        _snapshot(
            state=RunState.PAUSE_REQUESTED,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:35"
    assert page.timer_status_label.text() == "LIVE"

    # The actual PAUSED state begins at t=140.
    now[0] = 140.0

    page.render_snapshot(
        _snapshot(
            state=RunState.PAUSED,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:40"
    assert page.timer_status_label.text() == "PAUSED"
    assert page.timer_panel.property("timerState") == "paused"

    # One full minute passes in wall-clock time. Runtime must remain frozen.
    now[0] = 200.0
    page._refresh_runtime_cards()

    assert page.timer_value_label.text() == "00:00:40"
    assert page.timer_status_label.text() == "PAUSED"

    # RESUMING is still excluded from active runtime.
    now[0] = 205.0

    page.render_snapshot(
        _snapshot(
            state=RunState.RESUMING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:40"
    assert page.timer_status_label.text() == "RESUMING"

    # Observable RUNNING resumes at t=210.
    # Paused interval = 210 - 140 = 70 seconds.
    now[0] = 210.0

    page.render_snapshot(
        _snapshot(
            state=RunState.RUNNING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:40"
    assert page.timer_status_label.text() == "LIVE"

    # Ten more active seconds.
    now[0] = 220.0
    page._refresh_runtime_cards()

    assert page.timer_value_label.text() == "00:00:50"

    # Final wall duration = 130 seconds.
    # Minus 70 paused seconds = 60 active seconds.
    page.render_snapshot(
        _snapshot(
            state=RunState.COMPLETED,
            started_at=100.0,
            finished_at=230.0,
        )
    )

    assert page.timer_value_label.text() == "00:01:00"
    assert page.timer_status_label.text() == "FINAL"


def test_timer_accumulates_multiple_pause_intervals(
    qtbot,
    monkeypatch,
) -> None:
    now = [120.0]

    monkeypatch.setattr(
        "gow_monitor.ui.pages.overview_page.time.time",
        lambda: now[0],
    )

    page = OverviewPage()
    qtbot.addWidget(page)
    page.runtime_timer.stop()

    # First active interval: 20 s.
    page.render_snapshot(
        _snapshot(
            state=RunState.RUNNING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:20"

    # Pause 1: 120 -> 150 = 30 s excluded.
    page.render_snapshot(
        _snapshot(
            state=RunState.PAUSED,
            started_at=100.0,
        )
    )

    now[0] = 150.0

    page.render_snapshot(
        _snapshot(
            state=RunState.RUNNING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:20"

    # Second active interval: 150 -> 180 = 30 s.
    now[0] = 180.0
    page._refresh_runtime_cards()

    assert page.timer_value_label.text() == "00:00:50"

    # Pause 2: 180 -> 220 = 40 s excluded.
    page.render_snapshot(
        _snapshot(
            state=RunState.PAUSED,
            started_at=100.0,
        )
    )

    now[0] = 220.0

    page.render_snapshot(
        _snapshot(
            state=RunState.RUNNING,
            started_at=100.0,
        )
    )

    assert page.timer_value_label.text() == "00:00:50"

    # Final active interval: 220 -> 250 = 30 s.
    page.render_snapshot(
        _snapshot(
            state=RunState.COMPLETED,
            started_at=100.0,
            finished_at=250.0,
        )
    )

    # Wall = 150 s.
    # Paused = 30 + 40 = 70 s.
    # Active = 80 s.
    assert page.timer_value_label.text() == "00:01:20"
    assert page.timer_status_label.text() == "FINAL"
