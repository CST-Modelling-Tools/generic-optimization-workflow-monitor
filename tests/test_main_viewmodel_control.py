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


class RecordingRunResumer:
    def __init__(
        self,
        *,
        pid: int = 4242,
    ) -> None:
        self.pid = pid
        self.resume_calls: list[RunReference] = []

    def resume(
        self,
        run: RunReference,
    ) -> int:
        self.resume_calls.append(run)
        return self.pid


class FailingRunResumer:
    def __init__(self) -> None:
        self.resume_calls: list[RunReference] = []

    def resume(
        self,
        run: RunReference,
    ) -> int:
        self.resume_calls.append(run)
        raise RuntimeError("resume launch failed")


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


def test_viewmodel_resume_delegates_to_resumer_and_emits_state(
    qtbot,
    tmp_path: Path,
) -> None:
    resumer = RecordingRunResumer(
        pid=7319,
    )

    viewmodel = MainViewModel(
        run_resumer=resumer,
    )

    snapshot = _snapshot(
        tmp_path,
        state=RunState.PAUSED,
    )

    observed_states: list[RunState] = []
    observed_pids: list[int] = []

    viewmodel.run_state_changed.connect(
        observed_states.append
    )

    viewmodel.resume_request_succeeded.connect(
        observed_pids.append
    )

    pid = viewmodel.request_resume(
        snapshot
    )

    assert pid == 7319

    assert resumer.resume_calls == [
        snapshot.reference
    ]

    assert observed_states == [
        RunState.RESUMING
    ]

    assert observed_pids == [
        7319
    ]

    assert viewmodel.resource_monitor.gow_pid == 7319


@pytest.mark.parametrize(
    "state",
    [
        RunState.UNKNOWN,
        RunState.WAITING,
        RunState.RUNNING,
        RunState.PAUSE_REQUESTED,
        RunState.RESUMING,
        RunState.STOPPING,
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.STOPPED,
    ],
)
def test_viewmodel_resume_rejects_non_paused_states(
    qtbot,
    tmp_path: Path,
    state: RunState,
) -> None:
    resumer = RecordingRunResumer()

    viewmodel = MainViewModel(
        run_resumer=resumer,
    )

    snapshot = _snapshot(
        tmp_path,
        state=state,
    )

    with pytest.raises(
        ValueError,
        match="Resume can only be requested",
    ):
        viewmodel.request_resume(
            snapshot
        )

    assert resumer.resume_calls == []


def test_viewmodel_resume_does_not_emit_resuming_when_launch_fails(
    qtbot,
    tmp_path: Path,
) -> None:
    resumer = FailingRunResumer()

    viewmodel = MainViewModel(
        run_resumer=resumer,
    )

    snapshot = _snapshot(
        tmp_path,
        state=RunState.PAUSED,
    )

    observed_states: list[RunState] = []
    observed_pids: list[int] = []

    viewmodel.run_state_changed.connect(
        observed_states.append
    )

    viewmodel.resume_request_succeeded.connect(
        observed_pids.append
    )

    with pytest.raises(
        RuntimeError,
        match="resume launch failed",
    ):
        viewmodel.request_resume(
            snapshot
        )

    assert resumer.resume_calls == [
        snapshot.reference
    ]

    assert observed_states == []
    assert observed_pids == []