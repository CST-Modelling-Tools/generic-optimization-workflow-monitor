from __future__ import annotations

import json
from pathlib import Path

from gow_monitor.ui.main_window import MainWindow


def _write_result(
    run_root: Path,
    *,
    candidate_id: str,
    status: str = "ok",
    objective: float | None = 1.0,
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


def test_live_refresh_updates_counts_and_preserves_selected_run(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_a = results_root / "runs" / "run-a"
    run_b = results_root / "runs" / "run-b"

    _write_result(run_a, candidate_id="runa_g000000_c000000")
    _write_result(run_b, candidate_id="runb_g000000_c000000")

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)
    window.run_selector.setCurrentIndex(1)

    _write_result(run_b, candidate_id="runb_g000000_c000001")
    window.refresh_connected_results()

    qtbot.waitUntil(
        lambda: (
            window.current_snapshot is not None
            and window.current_snapshot.evaluation_count == 2
        ),
        timeout=3000,
    )

    assert window.run_selector.currentData() == "run-b"
    assert window.sidebar_evaluations.text() == "Evaluations: 2"
    assert window.auto_refresh_label.text() == "AUTO 1s"


def test_live_refresh_discovers_new_run_without_reselecting_folder(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_a = results_root / "runs" / "run-a"
    _write_result(run_a, candidate_id="runa_g000000_c000000")

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    run_b = results_root / "runs" / "run-b"
    _write_result(run_b, candidate_id="runb_g000000_c000000")
    window.refresh_connected_results()

    qtbot.waitUntil(lambda: window.run_selector.count() == 2, timeout=3000)

    assert window.run_selector.currentData() == "run-a"
    assert window.live_refresh.is_active


def test_live_refresh_detects_results_jsonl_completion(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    payload = _write_result(
        run_root,
        candidate_id="runlive_g000000_c000000",
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    assert window.state_label.text() == "RUNNING"

    (run_root / "results.jsonl").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )
    window.refresh_connected_results()

    qtbot.waitUntil(
        lambda: window.state_label.text() == "COMPLETED",
        timeout=3000,
    )

    assert window.current_snapshot is not None
    assert window.current_snapshot.evaluation_count == 1