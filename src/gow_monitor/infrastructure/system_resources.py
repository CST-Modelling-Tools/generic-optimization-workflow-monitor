from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import psutil

from gow_monitor.domain import SystemResourceSnapshot
from gow_monitor.infrastructure.gpu_resources import (
    GpuReader,
    GpuReaderRegistry,
    NvidiaSmiGpuReader,
    WindowsCimGpuReader,
    default_gpu_readers,
)


class SystemResourceReader:
    """Collect host-level CPU, RAM, core and optional GPU telemetry."""

    def __init__(
        self,
        *,
        active_core_threshold_percent: float = 5.0,
        gpu_readers: Sequence[GpuReader] | None = None,
        gpu_registry: GpuReaderRegistry | None = None,
        psutil_module: Any = psutil,
    ) -> None:
        if not 0.0 <= active_core_threshold_percent <= 100.0:
            raise ValueError(
                "active core threshold must be between 0 and 100"
            )

        if gpu_readers is not None and gpu_registry is not None:
            raise ValueError(
                "provide gpu_readers or gpu_registry, not both"
            )

        self.active_core_threshold_percent = (
            active_core_threshold_percent
        )
        self._psutil = psutil_module

        if gpu_registry is not None:
            self._gpu_registry = gpu_registry
        elif gpu_readers is not None:
            self._gpu_registry = GpuReaderRegistry(gpu_readers)
        else:
            self._gpu_registry = GpuReaderRegistry(
                default_gpu_readers()
            )

        self._prime_cpu_counters()

    def _prime_cpu_counters(self) -> None:
        self._psutil.cpu_percent(interval=None)
        self._psutil.cpu_percent(interval=None, percpu=True)

    def snapshot(self) -> SystemResourceSnapshot:
        cpu_percent = float(
            self._psutil.cpu_percent(interval=None)
        )

        per_core_percent = tuple(
            float(value)
            for value in self._psutil.cpu_percent(
                interval=None,
                percpu=True,
            )
        )

        logical_cores = self._psutil.cpu_count(logical=True)
        logical_cores = max(
            int(logical_cores or 0),
            len(per_core_percent),
            1,
        )

        physical_cores = self._psutil.cpu_count(logical=False)
        if physical_cores is not None and physical_cores < 1:
            physical_cores = None

        active_logical_cores = sum(
            value >= self.active_core_threshold_percent
            for value in per_core_percent
        )

        memory = self._psutil.virtual_memory()
        gpus, gpu_status = self._gpu_registry.read()

        return SystemResourceSnapshot(
            captured_at=time.time(),
            cpu_percent=min(100.0, max(0.0, cpu_percent)),
            per_core_percent=tuple(
                min(100.0, max(0.0, value))
                for value in per_core_percent
            ),
            physical_cores=physical_cores,
            logical_cores=int(logical_cores),
            active_logical_cores=active_logical_cores,
            active_core_threshold_percent=(
                self.active_core_threshold_percent
            ),
            memory_percent=min(
                100.0,
                max(0.0, float(memory.percent)),
            ),
            memory_used_bytes=int(memory.used),
            memory_total_bytes=int(memory.total),
            gpus=gpus,
            gpu_status=gpu_status,
        )


__all__ = [
    "GpuReader",
    "GpuReaderRegistry",
    "NvidiaSmiGpuReader",
    "SystemResourceReader",
    "WindowsCimGpuReader",
    "default_gpu_readers",
]
