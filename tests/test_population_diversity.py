from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from gow_monitor.domain import EvaluationPoint
from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.dashboard_metrics import population_diversity_series
from gow_monitor.ui.widgets import PopulationDiversityChart


def _point(
    evaluation: int,
    generation: int,
    *,
    x: float,
    y: float,
) -> EvaluationPoint:
    return EvaluationPoint(
        evaluation=evaluation,
        candidate_id=f"g{generation:06d}_c{evaluation:06d}",
        status="ok",
        objective=float(evaluation),
        best_so_far=1.0,
        mean_so_far=1.0,
        median_so_far=1.0,
        generation_id=generation,
        parameters=(("x", float(x)), ("y", float(y)), ("fixed", 7.0)),
    )


def test_dual_diversity_is_zero_for_collapsed_generation() -> None:
    history = (
        _point(1, 0, x=0.0, y=0.0),
        _point(2, 0, x=0.0, y=0.0),
    )

    samples = population_diversity_series(history)

    assert len(samples) == 1
    assert samples[0].spread == pytest.approx(0.0)
    assert samples[0].ellipse_area == pytest.approx(0.0)
    assert samples[0].active_dimensions == 0


def test_dual_diversity_calculates_spread_and_pca_ellipse_area() -> None:
    history = (
        _point(1, 0, x=0.0, y=0.0),
        _point(2, 0, x=1.0, y=0.0),
        _point(3, 0, x=0.0, y=1.0),
        _point(4, 0, x=1.0, y=1.0),
    )

    sample = population_diversity_series(history)[0]

    expected_spread = 2.0 / math.sqrt(3.0)
    expected_area = math.pi * 5.991464547107979 / 3.0
    assert sample.spread == pytest.approx(expected_spread)
    assert sample.diversity == pytest.approx(expected_spread)
    assert sample.ellipse_area == pytest.approx(expected_area, rel=1e-8)
    assert sample.active_dimensions == 2


def test_reader_extracts_generation_and_numeric_parameters(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-diversity"
    candidate_root = run_root / "candidate"
    candidate_root.mkdir(parents=True)

    payload = {
        "problem_id": "toy",
        "run_id": "run-diversity",
        "generation_id": 3,
        "candidate_id": "rabc_g000003_c000007",
        "candidate_local_id": "g000003_c000007",
        "attempt_id": "rabc_g000003_c000007_a000",
        "params": {
            "x": 0.25,
            "integer": 2,
            "enabled": True,
            "label": "ignored",
        },
        "fitness": {"status": "ok", "objective": 0.0625},
    }
    (candidate_root / "result.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    history = reader.history_of(reference)

    assert history[0].generation_id == 3
    assert history[0].parameter_map == {
        "integer": 2.0,
        "x": 0.25,
    }


def test_dual_diversity_chart_obeys_evaluation_window(qtbot) -> None:
    chart = PopulationDiversityChart()
    qtbot.addWidget(chart)
    history = (
        _point(1, 0, x=0.0, y=0.0),
        _point(2, 0, x=1.0, y=1.0),
        _point(3, 1, x=0.4, y=0.4),
        _point(4, 1, x=0.6, y=0.6),
    )
    chart.set_history(history)
    chart.set_window_size(2)

    assert len(chart.series) == 1
    assert chart.series[0].generation_id == 1
    assert hasattr(chart.series[0], "spread")
    assert hasattr(chart.series[0], "ellipse_area")
