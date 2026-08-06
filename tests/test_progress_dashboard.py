from __future__ import annotations

import json
from pathlib import Path

import pytest

from gow_monitor.domain import ObjectiveDirection
from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.main_window import MainWindow


def _write_result(
    run_root: Path,
    *,
    candidate_id: str,
    objective: float | None,
    status: str = "ok",
) -> dict[str, object]:
    candidate_root = run_root / candidate_id
    candidate_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "problem_id": "toy-progress",
        "run_id": run_root.name,
        "candidate_id": candidate_id,
        "attempt_id": f"{candidate_id}_a000",
        "fitness": {"status": status, "objective": objective},
    }
    (candidate_root / "result.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return payload


def _write_summary(
    results_root: Path,
    *,
    run_id: str,
    direction: str,
) -> None:
    results_root.mkdir(parents=True, exist_ok=True)
    (results_root / "summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "problem_id": "toy-progress",
                "objective": {"direction": direction},
            }
        ),
        encoding="utf-8",
    )


def test_reader_builds_minimize_progress_history(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-min"
    _write_summary(results_root, run_id="run-min", direction="minimize")

    _write_result(run_root, candidate_id="g000_c000", objective=5.0)
    _write_result(run_root, candidate_id="g000_c001", objective=3.0)
    _write_result(
        run_root,
        candidate_id="g000_c002",
        objective=None,
        status="failed",
    )
    _write_result(run_root, candidate_id="g000_c003", objective=4.0)

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot, history = reader.snapshot_and_history_of(reference)

    assert reference.direction is ObjectiveDirection.MINIMIZE
    assert snapshot.best_objective == pytest.approx(3.0)
    assert tuple(point.best_so_far for point in history) == (5.0, 3.0, 3.0, 3.0)
    assert history[1].mean_so_far == pytest.approx(4.0)
    assert history[1].median_so_far == pytest.approx(4.0)
    assert history[2].objective is None
    assert not history[2].is_valid
    assert history[3].mean_so_far == pytest.approx(4.0)
    assert history[3].median_so_far == pytest.approx(4.0)


def test_reader_builds_maximize_incumbent(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-max"
    _write_summary(results_root, run_id="run-max", direction="maximize")

    _write_result(run_root, candidate_id="g000_c000", objective=1.0)
    _write_result(run_root, candidate_id="g000_c001", objective=3.0)
    _write_result(run_root, candidate_id="g000_c002", objective=2.0)

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot, history = reader.snapshot_and_history_of(reference)

    assert reference.direction is ObjectiveDirection.MAXIMIZE
    assert snapshot.best_objective == pytest.approx(3.0)
    assert tuple(point.best_so_far for point in history) == (1.0, 3.0, 3.0)


def test_overview_renders_compact_progress_dashboard(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    _write_summary(results_root, run_id="run-live", direction="minimize")
    _write_result(run_root, candidate_id="g000_c000", objective=4.0)
    _write_result(run_root, candidate_id="g000_c001", objective=2.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    assert len(window.current_history) == 2
    assert window.overview_page.cards["best"].value_label.text() == "2"
    assert window.overview_page.cards["improvement"].value_label.text() == "50.00%"
    assert window.overview_page.progress_chart.history == window.current_history
    assert window.overview_page.run_health_panel.summary_label.text() == "HEALTHY"


def test_live_refresh_updates_progress_chart(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    _write_summary(results_root, run_id="run-live", direction="minimize")
    _write_result(run_root, candidate_id="g000_c000", objective=4.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    _write_result(run_root, candidate_id="g000_c001", objective=1.0)
    window.refresh_connected_results()

    qtbot.waitUntil(lambda: len(window.current_history) == 2, timeout=3000)

    assert window.overview_page.cards["best"].value_label.text() == "1"
    assert len(window.overview_page.progress_chart.history) == 2


def test_chart_window_selector_limits_visible_history(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-window"
    _write_summary(results_root, run_id="run-window", direction="minimize")

    for index in range(120):
        _write_result(
            run_root,
            candidate_id=f"g000_c{index:03d}",
            objective=float(120 - index),
        )

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    window.overview_page.window_selector.setCurrentIndex(2)

    assert window.overview_page.progress_chart.window_size == 100
    assert len(window.overview_page.progress_chart.visible_points()) == 100
