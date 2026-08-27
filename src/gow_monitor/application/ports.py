from __future__ import annotations

from typing import Protocol

from gow_monitor.domain.models import RunReference, RunSnapshot, RunState


class RunReaderPort(Protocol):
    def discover_runs(self) -> tuple[RunReference, ...]:
        """Return the GOW runs visible to the monitor."""

    def state_of(self, run: RunReference) -> RunState:
        """Determine the observable state of one run."""

    def snapshot_of(self, run: RunReference) -> RunSnapshot:
        """Return a filesystem-derived snapshot of one run."""


class RunControlPort(Protocol):
    def request_pause(self, run: RunReference) -> str:
        """Request a cooperative pause and return its request id."""

    def request_stop(self, run: RunReference) -> None:
        """Request a cooperative stop without killing the process."""

    def emergency_stop(self, run: RunReference) -> None:
        """Terminate a run when cooperative stop is unavailable."""
