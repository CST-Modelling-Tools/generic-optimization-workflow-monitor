from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ObjectiveDirection(str, Enum):
    UNKNOWN = "unknown"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class RunState(str, Enum):
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
    direction: ObjectiveDirection = ObjectiveDirection.UNKNOWN
    problem_id: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id cannot be empty")
        object.__setattr__(self, "run_root", Path(self.run_root).expanduser())


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    reference: RunReference
    state: RunState
    evaluation_count: int
    failed_evaluations: int
    result_sources: int

    def __post_init__(self) -> None:
        if self.evaluation_count < 0:
            raise ValueError("evaluation_count cannot be negative")
        if self.failed_evaluations < 0:
            raise ValueError("failed_evaluations cannot be negative")
        if self.failed_evaluations > self.evaluation_count:
            raise ValueError("failed_evaluations cannot exceed evaluation_count")
        if self.result_sources < 0:
            raise ValueError("result_sources cannot be negative")
