from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from gow_monitor.domain import RunState
from gow_monitor.ui.main_window import MainWindow


def _write_running_result(
    run_root: Path,
) -> None:
    candidate_id = "runpauseui_g000000_c000000"

    candidate_root = (
        run_root
        / candidate_id
    )

    candidate_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "problem_id": "toy-pause-ui",
        "run_id": run_root.name,
        "candidate_id": candidate_id,
        "attempt_id": (
            f"{candidate_id}_a000"
        ),
        "fitness": {
            "status": "ok",
            "objective": 1.0,
        },
    }

    (
        candidate_root
        / "result.json"
    ).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_pause_button_is_disabled_without_running_run(
    qtbot,
) -> None:
    window = MainWindow()

    qtbot.addWidget(window)

    assert "Pause" in window.pause_button.text()
    assert window.pause_button.objectName() == "runPauseButton"
    assert window.pause_button.parent() is window.overview_page
    assert window.header.layout().indexOf(window.pause_button) == -1
    assert (
        window.overview_page.timer_row.indexOf(
            window.pause_button
        )
        >= 0
    )
    assert (
        window.pause_button.size()
        == window.overview_page.timer_panel.size()
    )
    assert window.pause_button.width() == 300
    assert window.pause_button.height() == 50
    assert not window.pause_button.isEnabled()

    window.header.set_run_state(
        RunState.PAUSED
    )

    assert not window.pause_button.isEnabled()

    window.header.set_run_state(
        RunState.COMPLETED
    )

    assert not window.pause_button.isEnabled()

    window.header.set_run_state(
        RunState.RUNNING
    )

    assert window.pause_button.isEnabled()


def test_pause_button_writes_request_and_updates_ui_state(
    qtbot,
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"

    run_root = (
        results_root
        / "runs"
        / "run-pause-ui"
    )

    _write_running_result(
        run_root
    )

    window = MainWindow()

    qtbot.addWidget(window)

    window.connect_results_root(
        results_root
    )

    snapshot = window.current_snapshot

    assert snapshot is not None
    assert snapshot.state is RunState.RUNNING

    assert window.pause_button.isEnabled()
    assert window.state_label.text() == "RUNNING"

    qtbot.mouseClick(
        window.pause_button,
        Qt.MouseButton.LeftButton,
    )

    request_path = (
        run_root
        / "control"
        / "pause.request.json"
    )

    assert request_path.is_file()

    payload = json.loads(
        request_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["schema_version"] == 1
    assert payload["action"] == "pause"
    assert payload["requested_by"] == "gow-monitor"

    request_id = payload.get(
        "request_id"
    )

    assert isinstance(
        request_id,
        str,
    )
    assert request_id

    assert (
        window.state_label.text()
        == "PAUSE_REQUESTED"
    )

    assert not window.pause_button.isEnabled()
