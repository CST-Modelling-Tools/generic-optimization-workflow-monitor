from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from gow_monitor.domain import RunReference, RunState
from gow_monitor.ui.main_window import MainWindow


class RecordingRunResumer:
    def __init__(
        self,
        *,
        pid: int = 7319,
    ) -> None:
        self.pid = pid
        self.resume_calls: list[RunReference] = []

    def resume(
        self,
        run: RunReference,
    ) -> int:
        self.resume_calls.append(run)
        return self.pid


def _write_paused_run(
    run_root: Path,
) -> None:
    candidate_id = "runcontinueui_g000000_c000000"

    candidate_root = (
        run_root
        / candidate_id
    )

    candidate_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = {
        "problem_id": "toy-continue-ui",
        "run_id": run_root.name,
        "candidate_id": candidate_id,
        "attempt_id": f"{candidate_id}_a000",
        "fitness": {
            "status": "ok",
            "objective": 1.0,
        },
    }

    (
        candidate_root
        / "result.json"
    ).write_text(
        json.dumps(result),
        encoding="utf-8",
    )

    (
        run_root
        / "results.jsonl"
    ).write_text(
        json.dumps(result) + "\n",
        encoding="utf-8",
    )

    control_root = run_root / "control"
    control_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        control_root
        / "pause.ack.json"
    ).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "action": "pause",
                "request_id": "continue-ui-test",
                "status": "paused",
                "evaluations_done": 1,
                "completed_generations": 1,
            }
        ),
        encoding="utf-8",
    )

    checkpoint_root = run_root / "checkpoint"
    checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        checkpoint_root
        / "manifest.json"
    ).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_root.name,
                "status": "paused",
                "evaluations_done": 1,
                "completed_generations": 1,
                "next_generation": 1,
                "max_evaluations": 8,
            }
        ),
        encoding="utf-8",
    )


def test_continue_button_state_machine(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert "Continue" in window.continue_button.text()
    assert window.continue_button.objectName() == "runContinueButton"
    assert window.continue_button.parent() is window.overview_page
    assert window.header.layout().indexOf(window.continue_button) == -1
    assert (
        window.overview_page.timer_row.indexOf(
            window.continue_button
        )
        >= 0
    )
    assert (
        window.continue_button.size()
        == window.overview_page.timer_panel.size()
    )
    assert window.continue_button.width() == 300
    assert window.continue_button.height() == 50
    assert not window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()

    window.header.set_run_state(
        RunState.RUNNING
    )

    assert window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()

    window.header.set_run_state(
        RunState.PAUSE_REQUESTED
    )

    assert not window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()

    window.header.set_run_state(
        RunState.PAUSED
    )

    assert not window.pause_button.isEnabled()
    assert window.continue_button.isEnabled()

    window.header.set_run_state(
        RunState.RESUMING
    )

    assert not window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()

    window.header.set_run_state(
        RunState.COMPLETED
    )

    assert not window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()


def test_continue_button_resumes_paused_run_and_attaches_new_pid(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"

    run_root = (
        results_root
        / "runs"
        / "run-continue-ui"
    )

    _write_paused_run(
        run_root
    )

    window = MainWindow()
    qtbot.addWidget(window)

    resumer = RecordingRunResumer(
        pid=7319
    )

    window.viewmodel.run_resumer = resumer

    window.connect_results_root(
        results_root
    )

    snapshot = window.current_snapshot

    assert snapshot is not None
    assert snapshot.state is RunState.PAUSED

    assert window.state_label.text() == "PAUSED"
    assert not window.pause_button.isEnabled()
    assert window.continue_button.isEnabled()

    qtbot.mouseClick(
        window.continue_button,
        Qt.MouseButton.LeftButton,
    )

    assert resumer.resume_calls == [
        snapshot.reference
    ]

    assert window.state_label.text() == "RESUMING"

    assert not window.pause_button.isEnabled()
    assert not window.continue_button.isEnabled()

    assert window.resource_monitor.gow_pid == 7319
