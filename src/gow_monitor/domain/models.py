from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class RunState(StrEnum):
    UNKNOWN = "unknown"
    WAITING = "waiting"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class RunReference:
    run_id: str
    run_root: Path
    direction: ObjectiveDirection

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id cannot be empty")

        object.__setattr__(
            self,
            "run_root",
            Path(self.run_root).expanduser(),
        )
