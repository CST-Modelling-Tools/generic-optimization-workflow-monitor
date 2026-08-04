from __future__ import annotations

from types import SimpleNamespace

import psutil
import pytest

from gow_monitor.infrastructure.process_resources import GowProcessTreeReader


class _FakeProcess:
    def __init__(
        self,
        pid: int,
        *,
        name: str,
        cpu_values: tuple[float, ...],
        rss: int,
        threads: int,
        created_at: float,
        children: tuple[_FakeProcess, ...] = (),
        running: bool = True,
    ) -> None:
        self.pid = pid
        self._name = name
        self._cpu_values = cpu_values
        self._rss = rss
        self._threads = threads
        self._created_at = created_at
        self._children = children
        self._running = running
        self._cpu_index = 0

    def cpu_percent(self, interval=None) -> float:
        del interval
        index = min(self._cpu_index, len(self._cpu_values) - 1)
        value = self._cpu_values[index]
        self._cpu_index += 1
        return value

    def memory_info(self) -> SimpleNamespace:
        return SimpleNamespace(rss=self._rss)

    def num_threads(self) -> int:
        return self._threads

    def children(self, recursive: bool = False) -> list[_FakeProcess]:
        if not recursive:
            return list(self._children)

        discovered: list[_FakeProcess] = []
        pending = list(self._children)
        while pending:
            child = pending.pop(0)
            discovered.append(child)
            pending.extend(child._children)
        return discovered

    def is_running(self) -> bool:
        return self._running

    def status(self) -> str:
        return "running" if self._running else "stopped"

    def create_time(self) -> float:
        return self._created_at

    def name(self) -> str:
        return self._name


class _FakePsutil:
    STATUS_ZOMBIE = "zombie"

    def __init__(
        self,
        processes: tuple[_FakeProcess, ...],
        *,
        logical_cores: int = 4,
    ) -> None:
        self._processes = {
            process.pid: process
            for process in processes
        }
        self._logical_cores = logical_cores

    def Process(self, pid: int) -> _FakeProcess:
        try:
            return self._processes[pid]
        except KeyError as exc:
            raise psutil.NoSuchProcess(pid) from exc

    def cpu_count(self, *, logical: bool = True) -> int:
        if logical:
            return self._logical_cores
        return max(1, self._logical_cores // 2)


def _reader_fixture() -> tuple[GowProcessTreeReader, _FakeProcess]:
    grandchild = _FakeProcess(
        103,
        name="python-worker.exe",
        cpu_values=(0.0, 20.0),
        rss=50 * 1024**2,
        threads=2,
        created_at=103.0,
    )
    child = _FakeProcess(
        102,
        name="python.exe",
        cpu_values=(0.0, 60.0),
        rss=100 * 1024**2,
        threads=3,
        created_at=102.0,
        children=(grandchild,),
    )
    root = _FakeProcess(
        101,
        name="gow.exe",
        cpu_values=(0.0, 120.0),
        rss=200 * 1024**2,
        threads=5,
        created_at=101.0,
        children=(child,),
    )

    fake_psutil = _FakePsutil(
        (root, child, grandchild),
        logical_cores=4,
    )
    reader = GowProcessTreeReader(
        101,
        psutil_module=fake_psutil,
        clock=lambda: 1234.5,
    )
    return reader, root


def test_reader_aggregates_recursive_process_tree() -> None:
    reader, _root = _reader_fixture()

    snapshot = reader.snapshot()

    assert snapshot.available is True
    assert snapshot.root_pid == 101
    assert snapshot.root_name == "gow.exe"
    assert snapshot.process_count == 3
    assert snapshot.child_process_count == 2
    assert snapshot.thread_count == 10
    assert snapshot.memory_rss_bytes == 350 * 1024**2
    assert snapshot.cpu_process_percent == pytest.approx(200.0)
    assert snapshot.cpu_host_percent == pytest.approx(50.0)
    assert snapshot.logical_cores == 4
    assert snapshot.active_pids == (101, 102, 103)
    assert snapshot.captured_at == pytest.approx(1234.5)


def test_reader_without_attached_pid_returns_unavailable_snapshot() -> None:
    reader = GowProcessTreeReader(
        psutil_module=_FakePsutil(()),
        clock=lambda: 10.0,
    )

    snapshot = reader.snapshot()

    assert snapshot.available is False
    assert snapshot.root_pid is None
    assert snapshot.process_count is None
    assert snapshot.cpu_host_percent is None
    assert snapshot.status == "No GOW process is attached"


def test_reader_reports_finished_root_process() -> None:
    reader, root = _reader_fixture()
    root._running = False

    snapshot = reader.snapshot()

    assert snapshot.available is False
    assert snapshot.root_pid == 101
    assert "no longer running" in snapshot.status


def test_reader_can_detach_from_process() -> None:
    reader, _root = _reader_fixture()

    reader.detach()
    snapshot = reader.snapshot()

    assert reader.root_pid is None
    assert reader.is_attached is False
    assert snapshot.available is False


@pytest.mark.parametrize("invalid_pid", [0, -1])
def test_reader_rejects_non_positive_pid(invalid_pid: int) -> None:
    reader = GowProcessTreeReader(
        psutil_module=_FakePsutil(()),
    )

    with pytest.raises(ValueError):
        reader.attach(invalid_pid)


@pytest.mark.parametrize("invalid_pid", [True, 12.5, "123"])
def test_reader_rejects_non_integer_pid(invalid_pid: object) -> None:
    reader = GowProcessTreeReader(
        psutil_module=_FakePsutil(()),
    )

    with pytest.raises(TypeError):
        reader.attach(invalid_pid)  # type: ignore[arg-type]
