from __future__ import annotations

import json
from pathlib import Path

import pytest

from gow_monitor.domain import RunReference
from gow_monitor.infrastructure import (
    GowFilesystemRunController,
    InvalidExistingPauseRequestError,
    MissingRunRootError,
)


def _run_reference(
    tmp_path: Path,
    run_id: str = "run-control",
) -> RunReference:
    run_root = (
        tmp_path
        / "results"
        / "runs"
        / run_id
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return RunReference(
        run_id=run_id,
        run_root=run_root,
    )


def test_request_pause_creates_expected_control_artifact(
    tmp_path: Path,
) -> None:
    run = _run_reference(tmp_path)
    controller = GowFilesystemRunController()

    request_id = controller.request_pause(run)

    request_path = (
        run.run_root
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
    assert payload["request_id"] == request_id
    assert payload["requested_by"] == "gow-monitor"

    requested_at = payload.get(
        "requested_at"
    )

    assert isinstance(
        requested_at,
        str,
    )
    assert requested_at.endswith("Z")

    assert len(request_id) == 32
    assert request_id.isalnum()


def test_request_pause_is_idempotent_while_pending(
    tmp_path: Path,
) -> None:
    run = _run_reference(tmp_path)
    controller = GowFilesystemRunController()

    first_request_id = (
        controller.request_pause(run)
    )

    request_path = (
        run.run_root
        / "control"
        / "pause.request.json"
    )

    first_bytes = request_path.read_bytes()

    second_request_id = (
        controller.request_pause(run)
    )

    second_bytes = request_path.read_bytes()

    assert (
        second_request_id
        == first_request_id
    )

    assert second_bytes == first_bytes


def test_request_pause_rejects_malformed_existing_request(
    tmp_path: Path,
) -> None:
    run = _run_reference(tmp_path)

    request_path = (
        run.run_root
        / "control"
        / "pause.request.json"
    )

    request_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    request_path.write_text(
        "{this is not valid json",
        encoding="utf-8",
    )

    controller = GowFilesystemRunController()

    with pytest.raises(
        InvalidExistingPauseRequestError
    ):
        controller.request_pause(run)


def test_request_pause_requires_existing_run_root(
    tmp_path: Path,
) -> None:
    run = RunReference(
        run_id="missing-run",
        run_root=(
            tmp_path
            / "results"
            / "runs"
            / "missing-run"
        ),
    )

    controller = GowFilesystemRunController()

    with pytest.raises(
        MissingRunRootError
    ):
        controller.request_pause(run)


def test_pause_request_is_visible_to_filesystem_state_reader(
    tmp_path: Path,
) -> None:
    from gow_monitor.domain import RunState
    from gow_monitor.infrastructure import (
        GowFilesystemRunReader,
    )

    run = _run_reference(
        tmp_path,
        run_id="run-integration",
    )

    candidate_root = (
        run.run_root
        / "runintegration_g000000_c000000"
    )

    candidate_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_payload = {
        "problem_id": "toy-problem",
        "run_id": run.run_id,
        "candidate_id": (
            "runintegration_g000000_c000000"
        ),
        "attempt_id": (
            "runintegration_g000000_c000000_a000"
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
        json.dumps(result_payload),
        encoding="utf-8",
    )

    results_root = (
        tmp_path
        / "results"
    )

    reader = GowFilesystemRunReader(
        results_root
    )

    reference = reader.discover_runs()[0]

    assert (
        reader.state_of(reference)
        is RunState.RUNNING
    )

    controller = GowFilesystemRunController()

    request_id = controller.request_pause(
        reference
    )

    assert request_id

    assert (
        reader.state_of(reference)
        is RunState.PAUSE_REQUESTED
    )
