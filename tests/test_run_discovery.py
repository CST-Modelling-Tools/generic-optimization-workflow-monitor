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


def test_filesystem_reader_tracks_pause_control_states(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "run-pause"

    payload = _write_result(
        run_root,
        candidate_id="runpause_g000000_c000000",
        status="ok",
        objective=2.5,
    )

    # Real GOW campaigns finalize complete generations into shards.
    generation_root = run_root / "generations"
    generation_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    generation_path = (
        generation_root
        / "g000000.jsonl"
    )

    generation_path.write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]

    assert (
        reader.state_of(reference)
        is RunState.RUNNING
    )

    # --------------------------------------------------------
    # PAUSE REQUESTED
    # --------------------------------------------------------

    control_root = run_root / "control"

    control_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    request_payload = {
        "schema_version": 1,
        "action": "pause",
        "request_id": "monitor-test-request",
    }

    pause_request_path = (
        control_root
        / "pause.request.json"
    )

    pause_request_path.write_text(
        json.dumps(request_payload),
        encoding="utf-8",
    )

    assert (
        reader.state_of(reference)
        is RunState.PAUSE_REQUESTED
    )

    # --------------------------------------------------------
    # PAUSED
    # --------------------------------------------------------

    checkpoint_root = (
        run_root
        / "checkpoint"
    )

    checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    checkpoint_manifest = (
        checkpoint_root
        / "manifest.json"
    )

    paused_manifest = {
        "schema_version": 1,
        "run_id": "run-pause",
        "status": "paused",
        "evaluations_done": 1,
        "completed_generations": 1,
    }

    checkpoint_manifest.write_text(
        json.dumps(paused_manifest),
        encoding="utf-8",
    )

    # GOW materializes partial run-level results before emitting
    # the pause acknowledgement.
    (run_root / "results.jsonl").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    ack_payload = {
        **request_payload,
        "status": "paused",
        "evaluations_done": 1,
        "completed_generations": 1,
    }

    pause_ack_path = (
        control_root
        / "pause.ack.json"
    )

    pause_ack_path.write_text(
        json.dumps(ack_payload),
        encoding="utf-8",
    )

    pause_request_path.unlink()

    assert (
        reader.state_of(reference)
        is RunState.PAUSED
    )

    # --------------------------------------------------------
    # RUNNING AGAIN AFTER RESUME
    # --------------------------------------------------------

    running_manifest = {
        **paused_manifest,
        "status": "running",
    }

    checkpoint_manifest.write_text(
        json.dumps(running_manifest),
        encoding="utf-8",
    )

    # The old ACK deliberately remains present.
    assert pause_ack_path.is_file()

    assert (
        reader.state_of(reference)
        is RunState.RUNNING
    )

    # --------------------------------------------------------
    # COMPLETED
    # --------------------------------------------------------

    completed_manifest = {
        **paused_manifest,
        "status": "completed",
    }

    checkpoint_manifest.write_text(
        json.dumps(completed_manifest),
        encoding="utf-8",
    )

    assert (
        reader.state_of(reference)
        is RunState.COMPLETED
    )

    # RESUMING now exists as a domain state. Its temporary active
    # assignment will be implemented when Monitor launches resume.
    assert (
        RunState.RESUMING.value
        == "resuming"
    )
