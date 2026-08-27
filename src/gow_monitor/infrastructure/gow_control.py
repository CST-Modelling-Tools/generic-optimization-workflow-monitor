from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gow_monitor.domain import RunReference


PAUSE_REQUEST_FILENAME = "pause.request.json"


class GowRunControlError(RuntimeError):
    """Base error for Monitor-to-GOW control operations."""


class InvalidExistingPauseRequestError(GowRunControlError):
    """Raised when an existing pause request is malformed."""


class MissingRunRootError(GowRunControlError):
    """Raised when the selected run directory does not exist."""


class GowFilesystemRunController:
    """Control GOW runs exclusively through documented filesystem artifacts.

    The Monitor deliberately does not import GOW internals. A cooperative
    pause is requested by atomically creating:

        <run_root>/control/pause.request.json

    GOW consumes that artifact only at a safe completed-generation boundary.
    """

    @staticmethod
    def _utc_now_iso() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _pause_request_path(
        run: RunReference,
    ) -> Path:
        return (
            run.run_root
            / "control"
            / PAUSE_REQUEST_FILENAME
        )

    @staticmethod
    def _atomic_write_json(
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)

                json.dump(
                    payload,
                    handle,
                    indent=2,
                    sort_keys=True,
                )

                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary_path,
                path,
            )

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink(
                    missing_ok=True
                )

    @staticmethod
    def _read_existing_request(
        path: Path,
    ) -> dict[str, Any] | None:
        if not path.is_file():
            return None

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidExistingPauseRequestError(
                f"Existing pause request is not valid JSON: {path}"
            ) from exc

        if not isinstance(payload, dict):
            raise InvalidExistingPauseRequestError(
                "Existing pause request must contain a JSON object"
            )

        if payload.get("schema_version") != 1:
            raise InvalidExistingPauseRequestError(
                "Existing pause request has unsupported schema_version"
            )

        if payload.get("action") != "pause":
            raise InvalidExistingPauseRequestError(
                "Existing pause request action must be 'pause'"
            )

        request_id = payload.get("request_id")

        if (
            not isinstance(request_id, str)
            or not request_id.strip()
        ):
            raise InvalidExistingPauseRequestError(
                "Existing pause request requires a non-empty request_id"
            )

        return payload

    def request_pause(
        self,
        run: RunReference,
    ) -> str:
        """Create one cooperative pause request for a visible GOW run.

        The operation is idempotent while a valid request is already pending:
        repeated calls return the existing request id instead of replacing it.
        """

        if not run.run_root.is_dir():
            raise MissingRunRootError(
                f"GOW run root does not exist: {run.run_root}"
            )

        request_path = self._pause_request_path(
            run
        )

        existing = self._read_existing_request(
            request_path
        )

        if existing is not None:
            return str(existing["request_id"])

        request_id = uuid.uuid4().hex

        payload = {
            "schema_version": 1,
            "action": "pause",
            "request_id": request_id,
            "requested_at": self._utc_now_iso(),
            "requested_by": "gow-monitor",
        }

        self._atomic_write_json(
            request_path,
            payload,
        )

        return request_id
