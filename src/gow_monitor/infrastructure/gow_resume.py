from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
from pathlib import Path
from typing import Any

from gow_monitor.domain import RunReference

RUN_CONTEXT_FILENAME = "run_context.json"


class GowRunResumeError(RuntimeError):
    """Base error for launching a paused GOW run."""


class MissingRunContextError(GowRunResumeError):
    """Raised when a paused run has no resume context."""


class InvalidRunContextError(GowRunResumeError):
    """Raised when run_context.json violates its contract."""


class ResumeConfigMismatchError(GowRunResumeError):
    """Raised when the configured problem file changed after pause."""


class MissingResumeExecutableError(GowRunResumeError):
    """Raised when the recorded GOW Python executable is unavailable."""


class GowCliRunResumer:
    """Launch GOW's public resume CLI without importing GOW internals.

    The adapter consumes the run_context.json contract created by GOW:

        <run_root>/run_context.json

    It validates the run identity and configuration SHA-256 before spawning:

        python -m gow.cli resume CONFIG
            --outdir RESULTS_DIR
            --run-id RUN_ID
    """

    @staticmethod
    def _required_string(
        payload: dict[str, Any],
        key: str,
    ) -> str:
        value = payload.get(key)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise InvalidRunContextError(
                f"run_context.json requires a non-empty {key}"
            )

        return value.strip()

    @classmethod
    def _load_context(
        cls,
        run: RunReference,
    ) -> dict[str, Any]:
        if not run.run_root.is_dir():
            raise MissingRunContextError(
                f"GOW run root does not exist: {run.run_root}"
            )

        context_path = (
            run.run_root
            / RUN_CONTEXT_FILENAME
        )

        if not context_path.is_file():
            raise MissingRunContextError(
                f"Missing GOW resume context: {context_path}"
            )

        try:
            payload = json.loads(
                context_path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidRunContextError(
                f"Invalid GOW resume context JSON: {context_path}"
            ) from exc

        if not isinstance(payload, dict):
            raise InvalidRunContextError(
                "run_context.json must contain a JSON object"
            )

        if payload.get("schema_version") != 1:
            raise InvalidRunContextError(
                "Unsupported run_context.json schema_version"
            )

        saved_run_id = cls._required_string(
            payload,
            "run_id",
        )

        if saved_run_id != run.run_id:
            raise InvalidRunContextError(
                "run_context.json run_id does not match selected run"
            )

        return payload

    @classmethod
    def _validated_runtime(
        cls,
        run: RunReference,
        payload: dict[str, Any],
    ) -> tuple[
        Path,
        Path,
        Path,
    ]:
        config_path = Path(
            cls._required_string(
                payload,
                "config_path",
            )
        ).expanduser()

        if not config_path.is_absolute():
            raise InvalidRunContextError(
                "config_path must be absolute"
            )

        config_path = config_path.resolve()

        if not config_path.is_file():
            raise MissingRunContextError(
                f"Recorded GOW config does not exist: {config_path}"
            )

        saved_sha256 = cls._required_string(
            payload,
            "config_sha256",
        ).lower()

        if (
            len(saved_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in saved_sha256
            )
        ):
            raise InvalidRunContextError(
                "config_sha256 is not a valid SHA-256 digest"
            )

        actual_sha256 = hashlib.sha256(
            config_path.read_bytes()
        ).hexdigest()

        if not hmac.compare_digest(
            saved_sha256,
            actual_sha256,
        ):
            raise ResumeConfigMismatchError(
                "The GOW configuration changed after the run was paused"
            )

        python_executable = Path(
            cls._required_string(
                payload,
                "python_executable",
            )
        ).expanduser()

        if not python_executable.is_absolute():
            raise InvalidRunContextError(
                "python_executable must be absolute"
            )

        python_executable = (
            python_executable.resolve()
        )

        if not python_executable.is_file():
            raise MissingResumeExecutableError(
                "The Python executable recorded by GOW "
                f"does not exist: {python_executable}"
            )

        results_dir = Path(
            cls._required_string(
                payload,
                "results_dir",
            )
        ).expanduser()

        if not results_dir.is_absolute():
            raise InvalidRunContextError(
                "results_dir must be absolute"
            )

        results_dir = results_dir.resolve()

        if not results_dir.is_dir():
            raise MissingRunContextError(
                f"Recorded GOW results directory does not exist: "
                f"{results_dir}"
            )

        expected_run_root = (
            results_dir
            / "runs"
            / run.run_id
        ).resolve()

        actual_run_root = (
            run.run_root
            .resolve()
        )

        if expected_run_root != actual_run_root:
            raise InvalidRunContextError(
                "run_context.json results_dir does not match "
                "the selected run root"
            )

        return (
            config_path,
            python_executable,
            results_dir,
        )

    def resume(
        self,
        run: RunReference,
    ) -> int:
        """Spawn one independent GOW resume process and return its PID."""

        payload = self._load_context(
            run
        )

        (
            config_path,
            python_executable,
            results_dir,
        ) = self._validated_runtime(
            run,
            payload,
        )

        command = [
            str(python_executable),
            "-m",
            "gow.cli",
            "resume",
            str(config_path),
            "--outdir",
            str(results_dir),
            "--run-id",
            run.run_id,
        ]

        try:
            process = subprocess.Popen(
                command,
                cwd=str(config_path.parent),
            )
        except OSError as exc:
            raise GowRunResumeError(
                "Unable to launch the GOW resume process"
            ) from exc

        pid = getattr(
            process,
            "pid",
            None,
        )

        if (
            not isinstance(pid, int)
            or pid <= 0
        ):
            raise GowRunResumeError(
                "GOW resume process did not expose a valid PID"
            )

        return pid
