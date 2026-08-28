from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gow_monitor.domain import RunReference
from gow_monitor.infrastructure import (
    GowCliRunResumer,
    InvalidRunContextError,
    MissingResumeExecutableError,
    MissingRunContextError,
    ResumeConfigMismatchError,
)


class FakeProcess:
    pid = 43210


def _prepare_paused_run(
    tmp_path: Path,
) -> tuple[
    RunReference,
    Path,
    Path,
]:
    results_dir = (
        tmp_path
        / "results"
    )

    run_root = (
        results_dir
        / "runs"
        / "run-resume"
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_path = (
        tmp_path
        / "project"
        / "problem.yaml"
    )

    config_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_path.write_text(
        "id: resume-test\n",
        encoding="utf-8",
    )

    python_executable = (
        tmp_path
        / "gow-python.exe"
    )

    python_executable.write_bytes(
        b"fake-python"
    )

    context = {
        "schema_version": 1,
        "run_id": "run-resume",
        "config_path": str(
            config_path.resolve()
        ),
        "config_sha256": hashlib.sha256(
            config_path.read_bytes()
        ).hexdigest(),
        "python_executable": str(
            python_executable.resolve()
        ),
        "results_dir": str(
            results_dir.resolve()
        ),
    }

    (
        run_root
        / "run_context.json"
    ).write_text(
        json.dumps(context),
        encoding="utf-8",
    )

    return (
        RunReference(
            run_id="run-resume",
            run_root=run_root,
        ),
        config_path.resolve(),
        results_dir.resolve(),
    )


def test_resume_launches_public_gow_cli_and_returns_pid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        run,
        config_path,
        results_dir,
    ) = _prepare_paused_run(
        tmp_path
    )

    calls: list[
        tuple[
            list[str],
            str | None,
        ]
    ] = []

    def fake_popen(
        command,
        *,
        cwd=None,
    ):
        calls.append(
            (
                list(command),
                cwd,
            )
        )

        return FakeProcess()

    monkeypatch.setattr(
        "gow_monitor.infrastructure.gow_resume."
        "subprocess.Popen",
        fake_popen,
    )

    pid = GowCliRunResumer().resume(
        run
    )

    assert pid == 43210

    assert len(calls) == 1

    command, cwd = calls[0]

    assert command == [
        str(
            (
                tmp_path
                / "gow-python.exe"
            ).resolve()
        ),
        "-m",
        "gow.cli",
        "resume",
        str(config_path),
        "--outdir",
        str(results_dir),
        "--run-id",
        "run-resume",
    ]

    assert cwd == str(
        config_path.parent
    )


def test_resume_requires_run_context(
    tmp_path: Path,
) -> None:
    run_root = (
        tmp_path
        / "results"
        / "runs"
        / "missing-context"
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    run = RunReference(
        run_id="missing-context",
        run_root=run_root,
    )

    with pytest.raises(
        MissingRunContextError
    ):
        GowCliRunResumer().resume(
            run
        )


def test_resume_rejects_unsupported_context_schema(
    tmp_path: Path,
) -> None:
    run_root = (
        tmp_path
        / "results"
        / "runs"
        / "bad-schema"
    )

    run_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        run_root
        / "run_context.json"
    ).write_text(
        json.dumps(
            {
                "schema_version": 99,
                "run_id": "bad-schema",
            }
        ),
        encoding="utf-8",
    )

    run = RunReference(
        run_id="bad-schema",
        run_root=run_root,
    )

    with pytest.raises(
        InvalidRunContextError
    ):
        GowCliRunResumer().resume(
            run
        )


def test_resume_rejects_wrong_run_identity(
    tmp_path: Path,
) -> None:
    run, _, _ = _prepare_paused_run(
        tmp_path
    )

    context_path = (
        run.run_root
        / "run_context.json"
    )

    context = json.loads(
        context_path.read_text(
            encoding="utf-8"
        )
    )

    context["run_id"] = "different-run"

    context_path.write_text(
        json.dumps(context),
        encoding="utf-8",
    )

    with pytest.raises(
        InvalidRunContextError,
        match="run_id",
    ):
        GowCliRunResumer().resume(
            run
        )


def test_resume_rejects_changed_config(
    tmp_path: Path,
) -> None:
    run, config_path, _ = (
        _prepare_paused_run(
            tmp_path
        )
    )

    config_path.write_text(
        "id: modified-after-pause\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ResumeConfigMismatchError
    ):
        GowCliRunResumer().resume(
            run
        )


def test_resume_requires_recorded_python_executable(
    tmp_path: Path,
) -> None:
    run, _, _ = _prepare_paused_run(
        tmp_path
    )

    context_path = (
        run.run_root
        / "run_context.json"
    )

    context = json.loads(
        context_path.read_text(
            encoding="utf-8"
        )
    )

    missing_python = (
        tmp_path
        / "does-not-exist"
        / "python.exe"
    ).resolve()

    context["python_executable"] = str(
        missing_python
    )

    context_path.write_text(
        json.dumps(context),
        encoding="utf-8",
    )

    with pytest.raises(
        MissingResumeExecutableError
    ):
        GowCliRunResumer().resume(
            run
        )
