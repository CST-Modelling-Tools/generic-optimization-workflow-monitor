from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from gow_monitor.domain import (
    GowProcessResourceSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.infrastructure import (
    GowProcessTreeReader,
    SystemResourceReader,
)


@dataclass(frozen=True, slots=True)
class ResourceTelemetryPayload:
    system_snapshot: SystemResourceSnapshot | None = None
    system_error: str | None = None
    gow_snapshot: GowProcessResourceSnapshot | None = None
    gow_error: str | None = None


class _ResourceTaskSignals(QObject):
    completed = Signal(object)


class _ResourceTask(QRunnable):
    def __init__(
        self,
        system_reader: SystemResourceReader,
        gow_reader: GowProcessTreeReader,
    ) -> None:
        super().__init__()
        self.system_reader = system_reader
        self.gow_reader = gow_reader
        self.signals = _ResourceTaskSignals()

    @Slot()
    def run(self) -> None:
        system_snapshot: SystemResourceSnapshot | None = None
        system_error: str | None = None
        gow_snapshot: GowProcessResourceSnapshot | None = None
        gow_error: str | None = None

        try:
            system_snapshot = self.system_reader.snapshot()
        except Exception as exc:
            system_error = str(exc) or type(exc).__name__

        try:
            gow_snapshot = self.gow_reader.snapshot()
        except Exception as exc:
            gow_error = str(exc) or type(exc).__name__

        self.signals.completed.emit(
            ResourceTelemetryPayload(
                system_snapshot=system_snapshot,
                system_error=system_error,
                gow_snapshot=gow_snapshot,
                gow_error=gow_error,
            )
        )


class ResourceMonitorController(QObject):
    """Sample host and attached GOW resources outside the Qt UI thread."""

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
            raise ValueError("interval_ms must be at least 250 milliseconds")

        if gow_reader is not None and gow_pid is not None:
            raise ValueError("provide gow_reader or gow_pid, not both")

        self._reader = reader or SystemResourceReader()
        self._gow_reader = gow_reader or GowProcessTreeReader(gow_pid)
        self._sample_in_flight = False
        self._active_task: _ResourceTask | None = None

        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)

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

    def attach_gow_process(self, root_pid: int) -> None:
        self._gow_reader.attach(root_pid)

    def detach_gow_process(self) -> None:
        self._gow_reader.detach()

    def start(self) -> None:
        self._timer.start()
        self.sample_now()

    def stop(self) -> None:
        self._timer.stop()
        self._thread_pool.waitForDone(2500)

    @Slot()
    def sample_now(self) -> bool:
        if self._sample_in_flight:
            return False

        task = _ResourceTask(
            self._reader,
            self._gow_reader,
        )
        task.signals.completed.connect(self._sample_completed)

        self._sample_in_flight = True
        self._active_task = task
        self._thread_pool.start(task)
        return True

    @Slot(object)
    def _sample_completed(self, payload: object) -> None:
        self._sample_in_flight = False
        self._active_task = None

        if not isinstance(payload, ResourceTelemetryPayload):
            return

        if payload.system_snapshot is not None:
            self.sampled.emit(payload.system_snapshot)
        elif payload.system_error is not None:
            self.sample_failed.emit(payload.system_error)

        if payload.gow_snapshot is not None:
            self.gow_sampled.emit(payload.gow_snapshot)
        elif payload.gow_error is not None:
            self.gow_sample_failed.emit(payload.gow_error)
