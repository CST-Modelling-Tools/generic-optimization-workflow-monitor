from __future__ import annotations

from pathlib import Path

import pytest

from gow_monitor.domain import (
    EvaluationPoint,
    ObjectiveDirection,
    RunReference,
    RunSnapshot,
    RunState,
)
from gow_monitor.ui.dashboard_metrics import (
    objective_variability_percent,
    recent_improvement_percent,
    rolling_failure_rate_series,
)
from gow_monitor.ui.pages import OverviewPage
from gow_monitor.ui.widgets import ObjectiveProgressChart, SparklineWidget


def _point(
    evaluation: int,
    objective: float | None,
    best: float | None,
    *,
    status: str = "ok",
) -> EvaluationPoint:
    return EvaluationPoint(
        evaluation=evaluation,
        candidate_id=f"candidate-{evaluation}",
        status=status,
        objective=objective,
        best_so_far=best,
        mean_so_far=objective,
        median_so_far=objective,
    )


def _snapshot(
    *,
    direction: ObjectiveDirection = ObjectiveDirection.MINIMIZE,
) -> RunSnapshot:
    return RunSnapshot(
        reference=RunReference(
            run_id="run-dashboard",
            run_root=Path("results/runs/run-dashboard"),
            direction=direction,
            problem_id="toy-dashboard",
        ),
        state=RunState.COMPLETED,
        evaluation_count=3,
        failed_evaluations=0,
        result_sources=3,
        successful_evaluations=3,
        best_objective=2.0,
        latest_objective=2.0,
        mean_objective=4.0,
        median_objective=4.0,
        best_candidate_id="candidate-3",
    )


def test_recent_improvement_uses_latest_window() -> None:
    history = tuple(
        _point(index, float(201 - index), float(201 - index))
        for index in range(1, 201)
    )

    improvement = recent_improvement_percent(
        history,
        ObjectiveDirection.MINIMIZE,
        window_size=100,
    )

    assert improvement == pytest.approx(99.0 / 100.0 * 100.0)


def test_recent_improvement_respects_maximize_direction() -> None:
    history = (
        _point(1, 10.0, 10.0),
        _point(2, 12.0, 12.0),
        _point(3, 15.0, 15.0),
    )

    improvement = recent_improvement_percent(
        history,
        ObjectiveDirection.MAXIMIZE,
    )

    assert improvement == pytest.approx(50.0)


def test_chart_bounds_do_not_cross_zero_for_positive_series() -> None:
    lower, upper = ObjectiveProgressChart._expanded_bounds([0.001, 10.0, 20.0])

    assert lower == pytest.approx(0.0)
    assert upper > 20.0


def test_objective_variability_is_calculated_from_recent_values() -> None:
    history = (
        _point(1, 2.0, 2.0),
        _point(2, 4.0, 2.0),
        _point(3, 6.0, 2.0),
    )

    variability = objective_variability_percent(history)

    assert variability == pytest.approx(40.8248290463863)


def test_failure_rate_sparkline_reflects_recent_failures() -> None:
    history = (
        _point(1, 4.0, 4.0),
        _point(2, None, 4.0, status="failed"),
        _point(3, 3.0, 3.0),
    )

    series = rolling_failure_rate_series(history, window_size=2)

    assert series == pytest.approx((0.0, 50.0, 50.0))


def test_overview_renders_sparklines_and_lower_panels(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    history = (
        _point(1, 8.0, 8.0),
        _point(2, 4.0, 4.0),
        _point(3, 2.0, 2.0),
    )

    page.render_snapshot(_snapshot(), history)

    assert isinstance(page.cards["best"].sparkline, SparklineWidget)
    assert page.cards["best"].sparkline.values
    assert page.cards["improvement"].detail_label.text() == (
        "Over last 100 evaluations"
    )
    assert page.search_behavior_panel.tiles["valid_rate"].value_label.text() == (
        "100.00%"
    )
    assert (
        page.resources_panel.tiles["gow_memory"].value_label.text()
        == "N/A"
    )
    assert "gow_cpu" not in page.resources_panel.tiles
    assert "gpu" not in page.resources_panel.tiles
    assert "gow_processes" not in page.resources_panel.tiles
    assert "gow_threads" not in page.resources_panel.tiles
    assert page.resources_panel.tiles["sources"].value_label.text() == "3"
