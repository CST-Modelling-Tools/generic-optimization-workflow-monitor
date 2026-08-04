from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GowProcessResourceSnapshot:
    """Resource telemetry attributed to one GOW process tree.

    ``cpu_process_percent`` follows the process-oriented psutil convention and
    may exceed 100 percent when several logical CPUs are used simultaneously.

    ``cpu_host_percent`` normalizes that value against the logical CPU count and
    is therefore suitable for a 0-100 percent host-capacity gauge.
    """

    captured_at: float
    root_pid: int | None
    available: bool
    status: str
    cpu_process_percent: float | None = None
    cpu_host_percent: float | None = None
    memory_rss_bytes: int | None = None
    process_count: int | None = None
    child_process_count: int | None = None
    thread_count: int | None = None
    logical_cores: int | None = None
    active_pids: tuple[int, ...] = ()
    inaccessible_processes: int = 0
    root_name: str | None = None

    def __post_init__(self) -> None:
        if self.captured_at < 0:
            raise ValueError("captured_at cannot be negative")

        if self.root_pid is not None and self.root_pid < 1:
            raise ValueError("root_pid must be positive when available")

        if not self.status.strip():
            raise ValueError("status cannot be empty")

        if self.inaccessible_processes < 0:
            raise ValueError("inaccessible_processes cannot be negative")

        if len(set(self.active_pids)) != len(self.active_pids):
            raise ValueError("active_pids cannot contain duplicates")

        if any(pid < 1 for pid in self.active_pids):
            raise ValueError("active_pids must contain positive identifiers")

        if not self.available:
            return

        if self.root_pid is None:
            raise ValueError("an available snapshot requires root_pid")

        required_values = {
            "cpu_process_percent": self.cpu_process_percent,
            "cpu_host_percent": self.cpu_host_percent,
            "memory_rss_bytes": self.memory_rss_bytes,
            "process_count": self.process_count,
            "child_process_count": self.child_process_count,
            "thread_count": self.thread_count,
            "logical_cores": self.logical_cores,
        }
        missing = [
            name
            for name, value in required_values.items()
            if value is None
        ]
        if missing:
            raise ValueError(
                "available snapshots require all metrics: "
                + ", ".join(missing)
            )

        assert self.cpu_process_percent is not None
        assert self.cpu_host_percent is not None
        assert self.memory_rss_bytes is not None
        assert self.process_count is not None
        assert self.child_process_count is not None
        assert self.thread_count is not None
        assert self.logical_cores is not None

        if self.cpu_process_percent < 0:
            raise ValueError("process CPU utilization cannot be negative")

        if not 0.0 <= self.cpu_host_percent <= 100.0:
            raise ValueError(
                "host-normalized GOW CPU utilization must be between 0 and 100"
            )

        if self.memory_rss_bytes < 0:
            raise ValueError("GOW RSS memory cannot be negative")

        if self.process_count < 1:
            raise ValueError(
                "an available process tree must contain at least one process"
            )

        if not 0 <= self.child_process_count < self.process_count:
            raise ValueError(
                "child_process_count must be smaller than process_count"
            )

        if self.thread_count < 0:
            raise ValueError("thread_count cannot be negative")

        if self.logical_cores < 1:
            raise ValueError("logical_cores must be positive")

        if len(self.active_pids) != self.process_count:
            raise ValueError(
                "active_pids must contain every process represented by the snapshot"
            )

        if self.root_pid not in self.active_pids:
            raise ValueError("active_pids must contain root_pid")

    @classmethod
    def unavailable(
        cls,
        *,
        captured_at: float,
        status: str,
        root_pid: int | None = None,
    ) -> GowProcessResourceSnapshot:
        return cls(
            captured_at=captured_at,
            root_pid=root_pid,
            available=False,
            status=status,
        )
