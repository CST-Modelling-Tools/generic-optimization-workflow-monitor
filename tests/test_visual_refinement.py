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
from gow_monitor.ui.pages.overview_page import OverviewPage
from gow_monitor.ui.widgets import (
    ObjectiveProgressChart,
    SemicircleGauge,
    SparklineWidget,
)


def _point(
    evaluation: int,
    value: float,
    *,
    best: float | None = None,
) -> EvaluationPoint:
    return EvaluationPoint(
        evaluation=evaluation,
        candidate_id=f"candidate-{evaluation}",
        status="ok",
        objective=value,
        best_so_far=value if best is None else best,
        mean_so_far=value,
        median_so_far=value,
    )


def _snapshot(tmp_path: Path) -> RunSnapshot:
    reference = RunReference(
        run_id="run-visual",
        run_root=tmp_path / "results" / "runs" / "run-visual",
        direction=ObjectiveDirection.MINIMIZE,
        problem_id="toy-sphere-de",
    )
    return RunSnapshot(
        reference=reference,
        state=RunState.RUNNING,
        evaluation_count=4,
        failed_evaluations=1,
        result_sources=2,
        successful_evaluations=3,
        best_objective=0.5,
        latest_objective=0.75,
        mean_objective=1.25,
        median_objective=1.0,
        best_candidate_id="candidate-3",
    )


def test_semicircle_gauge_clamps_values(qtbot) -> None:
    gauge = SemicircleGauge()
    qtbot.addWidget(gauge)

    gauge.set_value(125.0, tone="good")
    assert gauge.value == pytest.approx(100.0)
    assert gauge.tone == "good"

    gauge.set_value(-4.0, tone="bad")
    assert gauge.value == pytest.approx(0.0)
    assert gauge.tone == "bad"

    gauge.set_value(None)
    assert gauge.value is None


def test_overview_uses_rate_gauges(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)

    assert isinstance(page.cards["best"].sparkline, SparklineWidget)
    assert isinstance(page.cards["success"].gauge, SemicircleGauge)
    assert isinstance(page.cards["failures"].gauge, SemicircleGauge)


def test_overview_updates_gauges_and_compact_footer(qtbot, tmp_path: Path) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    history = (
        _point(1, 4.0),
        _point(2, 2.0),
        _point(3, 0.5),
    )

    page.render_snapshot(_snapshot(tmp_path), history)

    assert page.cards["success"].gauge is not None
    assert page.cards["success"].gauge.value == pytest.approx(75.0)
    assert page.cards["failures"].gauge is not None
    assert page.cards["failures"].gauge.value == pytest.approx(25.0)
    assert "Run root" not in page.chart_footer.text()
    assert "run-visual" in page.chart_footer.toolTip()


def test_search_behavior_valid_rate_uses_gauge(qtbot, tmp_path: Path) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    page.render_snapshot(
        _snapshot(tmp_path),
        (_point(1, 4.0), _point(2, 2.0), _point(3, 0.5)),
    )

    tile = page.search_behavior_panel.tiles["valid_rate"]
    assert isinstance(tile.gauge, SemicircleGauge)
    assert tile.gauge.value == pytest.approx(75.0)


def test_chart_uses_log_scale_for_large_positive_dynamic_range(qtbot) -> None:
    chart = ObjectiveProgressChart()
    qtbot.addWidget(chart)
    chart.set_history(
        (
            _point(1, 40.0),
            _point(2, 2.0),
            _point(3, 0.001),
        ),
        ObjectiveDirection.MINIMIZE,
    )

    assert chart.effective_scale() == "log"


def test_chart_keeps_linear_scale_for_compact_or_signed_ranges(qtbot) -> None:
    chart = ObjectiveProgressChart()
    qtbot.addWidget(chart)

    chart.set_history(
        (_point(1, 15.0), _point(2, 13.0), _point(3, 12.0)),
        ObjectiveDirection.MINIMIZE,
    )
    assert chart.effective_scale() == "linear"

    chart.set_history(
        (_point(1, 2.0), _point(2, -1.0), _point(3, -2.0)),
        ObjectiveDirection.MINIMIZE,
    )
    assert chart.effective_scale() == "linear"
