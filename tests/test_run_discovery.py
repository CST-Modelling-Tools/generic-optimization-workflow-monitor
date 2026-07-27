from __future__ import annotations

import json
from pathlib import Path

from gow_monitor.domain import ObjectiveDirection, RunState
from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.main_window import MainWindow


def _write_result(
    run_root: Path,
    *,
    candidate_id: str,
    status: str,
    objective: float | None,
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


def test_filesystem_reader_discovers_and_summarizes_runs(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_a = results_root / "runs" / "run-a"
    run_b = results_root / "runs" / "run-b"
    run_b.mkdir(parents=True)

    first = _write_result(
        run_a,
        candidate_id="runa_g000000_c000000",
        status="ok",
        objective=3.0,
    )
    second = _write_result(
        run_a,
        candidate_id="runa_g000000_c000001",
        status="failed",
        objective=None,
    )
    (results_root / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-a",
                "problem_id": "toy-sphere-de",
                "objective": {"direction": "minimize"},
            }
        ),
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    references = reader.discover_runs()

    assert tuple(item.run_id for item in references) == ("run-a", "run-b")
    assert references[0].direction is ObjectiveDirection.MINIMIZE
    assert references[0].problem_id == "toy-sphere-de"

    snapshot = reader.snapshot_of(references[0])
    assert snapshot.state is RunState.RUNNING
    assert snapshot.evaluation_count == 2
    assert snapshot.failed_evaluations == 1
    assert snapshot.result_sources == 2

    with (run_a / "results.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(first) + "\n")
        handle.write(json.dumps(second) + "\n")

    completed = reader.snapshot_of(references[0])
    assert completed.state is RunState.COMPLETED
    assert completed.evaluation_count == 2
    assert completed.failed_evaluations == 1


def test_desktop_shell_connects_results_directory(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-live"
    _write_result(
        run_root,
        candidate_id="runlive_g000000_c000000",
        status="ok",
        objective=1.5,
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(results_root)

    assert window.run_selector.count() == 1
    assert window.run_selector.currentData() == "run-live"

    snapshot = window.current_snapshot
    assert snapshot is not None
    assert snapshot.reference.run_id == "run-live"
    assert snapshot.evaluation_count == 1
    assert "run-live" in window.job_label.text()
    assert window.state_label.text() == "RUNNING"
