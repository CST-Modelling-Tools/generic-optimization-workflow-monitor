from __future__ import annotations

import threading
import time
from pathlib import Path

from gow_monitor.domain import (
    GowProcessResourceSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.infrastructure.process_resources import (
    discover_gow_process_pid,
)
from gow_monitor.ui.resource_monitor import ResourceMonitorController


class _FastSystemReader:
    def __init__(self) -> None:
        self.count = 0

    def snapshot(self) -> SystemResourceSnapshot:
        self.count += 1
        return SystemResourceSnapshot(
            captured_at=time.time(),
            cpu_percent=10.0,
            per_core_percent=(10.0, 10.0),
            physical_cores=1,
            logical_cores=2,
            active_logical_cores=2,
            active_core_threshold_percent=5.0,
            memory_percent=20.0 + self.count,
            memory_used_bytes=(2 + self.count) * 1024**3,
            memory_total_bytes=16 * 1024**3,
            gpus=(),
            gpu_status="disabled",
        )


class _SlowGowReader:
    root_pid = 123

    def __init__(self) -> None:
        self.release = threading.Event()

    @staticmethod
    def attach(root_pid: int) -> None:
        del root_pid

    @staticmethod
    def detach() -> None:
        return None

    def snapshot(self) -> GowProcessResourceSnapshot:
        self.release.wait(timeout=5.0)
        return GowProcessResourceSnapshot.unavailable(
            captured_at=time.time(),
            root_pid=123,
            status="synthetic blocked process reader",
        )


class _FakeProcess:
    def __init__(
        self,
        *,
        pid: int,
        name: str,
        cmdline: tuple[str, ...],
        created_at: float,
    ) -> None:
        self.info = {
            "pid": pid,
            "name": name,
            "cmdline": list(cmdline),
            "create_time": created_at,
        }


class _FakePsutil:
    def __init__(self, processes: tuple[_FakeProcess, ...]) -> None:
        self.processes = processes

    def process_iter(self, attrs=()):
        del attrs
        return iter(self.processes)


def test_host_sampling_continues_while_gow_sampling_is_busy(qtbot) -> None:
    system_reader = _FastSystemReader()
    gow_reader = _SlowGowReader()
    controller = ResourceMonitorController(
        interval_ms=250,
        reader=system_reader,  # type: ignore[arg-type]
        gow_reader=gow_reader,  # type: ignore[arg-type]
    )
    host_snapshots: list[SystemResourceSnapshot] = []
    controller.sampled.connect(host_snapshots.append)

    try:
        controller.start()
        qtbot.waitUntil(
            lambda: len(host_snapshots) >= 3,
            timeout=2000,
        )
    finally:
        gow_reader.release.set()
        controller.stop()

    assert len(host_snapshots) >= 3
    assert host_snapshots[-1].memory_percent > (
        host_snapshots[0].memory_percent
    )


def test_process_discovery_prefers_matching_run_id(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    matching = _FakeProcess(
        pid=222,
        name="gow.exe",
        cmdline=(
            "C:/gow/.venv/Scripts/gow.exe",
            "run",
            "spec.yaml",
            "--outdir",
            str(results_root),
            "--run-id",
            "target-run",
        ),
        created_at=20.0,
    )
    other = _FakeProcess(
        pid=111,
        name="gow.exe",
        cmdline=(
            "C:/gow/.venv/Scripts/gow.exe",
            "run",
            "spec.yaml",
            "--outdir",
            str(results_root),
            "--run-id",
            "other-run",
        ),
        created_at=30.0,
    )

    pid = discover_gow_process_pid(
        results_root=results_root,
        run_id="target-run",
        psutil_module=_FakePsutil((other, matching)),
    )

    assert pid == 222


def test_process_discovery_returns_none_for_ambiguous_outdir(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    first = _FakeProcess(
        pid=111,
        name="gow.exe",
        cmdline=(
            "gow.exe",
            "run",
            "a.yaml",
            "--outdir",
            str(results_root),
        ),
        created_at=10.0,
    )
    second = _FakeProcess(
        pid=222,
        name="gow.exe",
        cmdline=(
            "gow.exe",
            "run",
            "b.yaml",
            "--outdir",
            str(results_root),
        ),
        created_at=20.0,
    )

    pid = discover_gow_process_pid(
        results_root=results_root,
        run_id="generated-run-id",
        psutil_module=_FakePsutil((first, second)),
    )

    assert pid is None
