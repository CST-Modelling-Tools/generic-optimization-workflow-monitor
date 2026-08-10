from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from gow_monitor.domain import (
    GowProcessResourceSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.infrastructure import (
    GowProcessTreeReader,
    SystemResourceReader,
)
from gow_monitor.infrastructure.process_resources import (
    discover_gow_process_pid,
)


@dataclass(frozen=True, slots=True)
class _SystemTaskResult:
    snapshot: SystemResourceSnapshot | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _GowTaskResult:
    snapshot: GowProcessResourceSnapshot | None = None
    error: str | None = None


class _ResourceTaskSignals(QObject):
    completed = Signal(object)


class _SystemResourceTask(QRunnable):
    def __init__(self, reader: SystemResourceReader) -> None:
        super().__init__()
        self.reader = reader
        self.signals = _ResourceTaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            snapshot = self.reader.snapshot()
        except Exception as exc:
            self.signals.completed.emit(
                _SystemTaskResult(
                    error=str(exc) or type(exc).__name__,
                )
            )
            return

        self.signals.completed.emit(
            _SystemTaskResult(snapshot=snapshot)
        )


class _GowResourceTask(QRunnable):
    def __init__(
        self,
        reader: GowProcessTreeReader,
        *,
        auto_discover: bool,
        results_root: Path | None,
        run_id: str | None,
    ) -> None:
        super().__init__()
        self.reader = reader
        self.auto_discover = auto_discover
        self.results_root = results_root
        self.run_id = run_id
        self.signals = _ResourceTaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            self._ensure_attachment()
            snapshot = self.reader.snapshot()

            if (
                self.auto_discover
                and not snapshot.available
                and self.reader.root_pid is not None
                and (
                    "no longer" in snapshot.status.lower()
                    or "disappeared" in snapshot.status.lower()
                )
            ):
                self.reader.detach()
        except Exception as exc:
            self.signals.completed.emit(
                _GowTaskResult(
                    error=str(exc) or type(exc).__name__,
                )
            )
            return

        self.signals.completed.emit(
            _GowTaskResult(snapshot=snapshot)
        )

    def _ensure_attachment(self) -> None:
        if not self.auto_discover:
            return
        if self.reader.root_pid is not None:
            return
        if self.results_root is None:
            return

        discovered_pid = discover_gow_process_pid(
            results_root=self.results_root,
            run_id=self.run_id,
            exclude_pids=(os.getpid(),),
        )
        if discovered_pid is not None:
            self.reader.attach(discovered_pid)


class ResourceMonitorController(QObject):
    """Sample host and GOW resources independently outside the UI thread."""

    sampled = Signal(object)
    sample_failed = Signal(str)
    gow_sampled = Signal(object)
    gow_sample_failed = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        interval_ms: int = 1000,
        reader: SystemResourceReader | None = None,
        gow_reader: GowProcessTreeReader | None = None,
        gow_pid: int | None = None,
    ) -> None:
        super().__init__(parent)

        if interval_ms < 250:
            raise ValueError(
                "interval_ms must be at least 250 milliseconds"
            )

        if gow_reader is not None and gow_pid is not None:
            raise ValueError("provide gow_reader or gow_pid, not both")

        # The Resources panel exposes host CPU/RAM/cores but no GPU card.
        # Avoid hidden GPU probes in the fast host-telemetry path.
        self._reader = reader or SystemResourceReader(gpu_readers=())
        self._gow_reader = gow_reader or GowProcessTreeReader(gow_pid)

        self._auto_discover_gow = (
            gow_reader is None and gow_pid is None
        )
        self._watched_results_root: Path | None = None
        self._watched_run_id: str | None = None

        self._system_sample_in_flight = False
        self._gow_sample_in_flight = False
        self._active_system_task: _SystemResourceTask | None = None
        self._active_gow_task: _GowResourceTask | None = None

        self._system_thread_pool = QThreadPool(self)
        self._system_thread_pool.setMaxThreadCount(1)

        self._gow_thread_pool = QThreadPool(self)
        self._gow_thread_pool.setMaxThreadCount(1)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.sample_now)

    @property
    def interval_ms(self) -> int:
        return self._timer.interval()

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    @property
    def gow_pid(self) -> int | None:
        return self._gow_reader.root_pid

    @property
    def auto_discover_gow(self) -> bool:
        return self._auto_discover_gow

    def watch_gow_run(
        self,
        *,
        results_root: str | Path,
        run_id: str,
    ) -> None:
        self._watched_results_root = (
            Path(results_root).expanduser().resolve()
        )
        self._watched_run_id = str(run_id)

    def attach_gow_process(self, root_pid: int) -> None:
        self._auto_discover_gow = False
        self._gow_reader.attach(root_pid)

    def detach_gow_process(self) -> None:
        self._gow_reader.detach()

    def start(self) -> None:
        self._timer.start()
        self.sample_now()

    def stop(self) -> None:
        self._timer.stop()
        self._system_thread_pool.waitForDone(2500)
        self._gow_thread_pool.waitForDone(2500)

    @Slot()
    def sample_now(self) -> bool:
        system_started = self._sample_system_now()
        gow_started = self._sample_gow_now()
        return system_started or gow_started

    def _sample_system_now(self) -> bool:
        if self._system_sample_in_flight:
            return False

        task = _SystemResourceTask(self._reader)
        task.signals.completed.connect(
            self._system_sample_completed
        )
        self._system_sample_in_flight = True
        self._active_system_task = task
        self._system_thread_pool.start(task)
        return True

    def _sample_gow_now(self) -> bool:
        if self._gow_sample_in_flight:
            return False

        task = _GowResourceTask(
            self._gow_reader,
            auto_discover=self._auto_discover_gow,
            results_root=self._watched_results_root,
            run_id=self._watched_run_id,
        )
        task.signals.completed.connect(
            self._gow_sample_completed
        )
        self._gow_sample_in_flight = True
        self._active_gow_task = task
        self._gow_thread_pool.start(task)
        return True

    @Slot(object)
    def _system_sample_completed(self, payload: object) -> None:
        self._system_sample_in_flight = False
        self._active_system_task = None

        if not isinstance(payload, _SystemTaskResult):
            return

        if payload.snapshot is not None:
            self.sampled.emit(payload.snapshot)
        elif payload.error is not None:
            self.sample_failed.emit(payload.error)

    @Slot(object)
    def _gow_sample_completed(self, payload: object) -> None:
        self._gow_sample_in_flight = False
        self._active_gow_task = None

        if not isinstance(payload, _GowTaskResult):
            return

        if payload.snapshot is not None:
            self.gow_sampled.emit(payload.snapshot)
        elif payload.error is not None:
            self.gow_sample_failed.emit(payload.error)
