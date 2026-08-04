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
        "problem_id": "toy-sphere-de",
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


def test_reader_calculates_minimize_kpis(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-min"

    _write_result(run_root, candidate_id="g000000_c000000", objective=3.0)
    _write_result(run_root, candidate_id="g000000_c000001", objective=1.0)
    _write_result(run_root, candidate_id="g000000_c000002", objective=2.0)
    _write_result(
        run_root,
        candidate_id="g000000_c000003",
        objective=None,
        status="failed",
    )
    (results_root / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-min",
                "problem_id": "toy-sphere-de",
                "objective": {"direction": "minimize"},
            }
        ),
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot = reader.snapshot_of(reference)

    assert reference.direction is ObjectiveDirection.MINIMIZE
    assert snapshot.evaluation_count == 4
    assert snapshot.successful_evaluations == 3
    assert snapshot.failed_evaluations == 1
    assert snapshot.best_objective == pytest.approx(1.0)
    assert snapshot.latest_objective == pytest.approx(2.0)
    assert snapshot.mean_objective == pytest.approx(2.0)
    assert snapshot.median_objective == pytest.approx(2.0)
    assert snapshot.best_candidate_id == "g000000_c000001"
    assert snapshot.success_rate == pytest.approx(0.75)


def test_reader_respects_maximize_direction(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-max"

    _write_result(run_root, candidate_id="g000000_c000000", objective=1.0)
    _write_result(run_root, candidate_id="g000000_c000001", objective=3.0)
    _write_result(run_root, candidate_id="g000000_c000002", objective=2.0)
    (results_root / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-max",
                "problem_id": "toy-sphere-de",
                "objective": {"direction": "maximize"},
            }
        ),
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot = reader.snapshot_of(reference)

    assert reference.direction is ObjectiveDirection.MAXIMIZE
    assert snapshot.best_objective == pytest.approx(3.0)
    assert snapshot.best_candidate_id == "g000000_c000001"


def test_overview_renders_kpis_and_ascii_labels(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    _write_result(run_root, candidate_id="g000000_c000000", objective=2.0)
    _write_result(run_root, candidate_id="g000000_c000001", objective=1.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    assert window.overview_page.cards["evaluations"].value_label.text() == "2"
    assert window.overview_page.cards["best"].value_label.text() == "1"
    assert window.brand_label.text() == "GOW"
    assert window.version_label.text() == "Framework foundation | v0.1.0"
    assert "|" in window.run_selector.currentText()
    assert all(ord(character) < 128 for character in window.brand_label.text())
    assert all(ord(character) < 128 for character in window.run_selector.currentText())


def test_live_refresh_updates_overview_best_objective(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    _write_result(run_root, candidate_id="g000000_c000000", objective=2.0)

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)
    assert window.overview_page.cards["best"].value_label.text() == "2"

    _write_result(run_root, candidate_id="g000000_c000001", objective=0.5)
    window.refresh_connected_results()

    qtbot.waitUntil(
        lambda: window.overview_page.cards["best"].value_label.text() == "0.5",
        timeout=3000,
    )

    assert window.overview_page.cards["evaluations"].value_label.text() == "2"