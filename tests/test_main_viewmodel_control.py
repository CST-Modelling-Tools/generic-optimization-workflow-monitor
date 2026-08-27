from __future__ import annotations

from pathlib import Path

import pytest

from gow_monitor.domain import (
    RunReference,
    RunSnapshot,
    RunState,
)
from gow_monitor.ui.main_viewmodel import MainViewModel


class RecordingRunController:
    def __init__(self) -> None:
        self.pause_calls: list[RunReference] = []

    def request_pause(
        self,
        run: RunReference,
    ) -> str:
        self.pause_calls.append(run)
        return "request-from-test"

    def request_stop(
        self,
        run: RunReference,
    ) -> None:
        del run

    def emergency_stop(
        self,
        run: RunReference,
    ) -> None:
        del run


def _snapshot(
    tmp_path: Path,
    *,
    state: RunState,
) -> RunSnapshot:
    run_root = (
        tmp_path
        / "results"
        / "runs"
        / "run-viewmodel"
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    reference = RunReference(
        run_id="run-viewmodel",
        run_root=run_root,
    )

    return RunSnapshot(
        reference=reference,
        state=state,
        evaluation_count=1,
        failed_evaluations=0,
        result_sources=1,
        successful_evaluations=1,
    )


def test_viewmodel_pause_delegates_to_controller_and_emits_state(
    qtbot,
    tmp_path: Path,
) -> None:
    controller = RecordingRunController()

    viewmodel = MainViewModel(
        run_controller=controller,
    )

    snapshot = _snapshot(
        tmp_path,
        state=RunState.RUNNING,
    )

    observed_states: list[RunState] = []
    observed_request_ids: list[str] = []

    viewmodel.run_state_changed.connect(
        observed_states.append
    )

    viewmodel.pause_request_succeeded.connect(
        observed_request_ids.append
    )

    request_id = viewmodel.request_pause(
        snapshot
    )

    assert request_id == "request-from-test"

    assert controller.pause_calls == [
        snapshot.reference
    ]

    assert observed_states == [
        RunState.PAUSE_REQUESTED
    ]

    assert observed_request_ids == [
        "request-from-test"
    ]


@pytest.mark.parametrize(
    "state",
    [
        RunState.UNKNOWN,
        RunState.WAITING,
        RunState.PAUSE_REQUESTED,
        RunState.PAUSED,
        RunState.RESUMING,
        RunState.STOPPING,
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.STOPPED,
    ],
)
def test_viewmodel_pause_rejects_non_running_states(
    qtbot,
    tmp_path: Path,
    state: RunState,
) -> None:
    controller = RecordingRunController()

    viewmodel = MainViewModel(
        run_controller=controller,
    )

    snapshot = _snapshot(
        tmp_path,
        state=state,
    )

    with pytest.raises(
        ValueError,
        match="Pause can only be requested",
    ):
        viewmodel.request_pause(
            snapshot
        )

    assert controller.pause_calls == []
