from __future__ import annotations

from types import SimpleNamespace

import pytest

from gow_monitor.domain import (
    GpuResourceSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.infrastructure.system_resources import (
    NvidiaSmiGpuReader,
    SystemResourceReader,
)


class _FakePsutil:
    def cpu_percent(
        self,
        interval: float | None = None,
        *,
        percpu: bool = False,
    ):
        del interval
        if percpu:
            return [0.0, 10.0, 80.0, 100.0]
        return 47.5

    @staticmethod
    def cpu_count(*, logical: bool = True) -> int:
        return 4 if logical else 2

    @staticmethod
    def virtual_memory() -> SimpleNamespace:
        return SimpleNamespace(
            percent=62.5,
            used=5 * 1024**3,
            total=8 * 1024**3,
        )


class _FakeGpuReader:
    backend_name = "fake-gpu"
    is_available = True

    @staticmethod
    def read() -> tuple[GpuResourceSnapshot, ...]:
        return (
            GpuResourceSnapshot(
                name="Test GPU",
                utilization_percent=73.0,
                memory_used_bytes=2 * 1024**3,
                memory_total_bytes=8 * 1024**3,
                backend="fake-gpu",
            ),
        )


def test_system_resource_reader_collects_host_metrics() -> None:
    reader = SystemResourceReader(
        active_core_threshold_percent=5.0,
        gpu_readers=(_FakeGpuReader(),),
        psutil_module=_FakePsutil(),
    )

    snapshot = reader.snapshot()

    assert snapshot.cpu_percent == pytest.approx(47.5)
    assert snapshot.per_core_percent == pytest.approx((0.0, 10.0, 80.0, 100.0))
    assert snapshot.physical_cores == 2
    assert snapshot.logical_cores == 4
    assert snapshot.active_logical_cores == 3
    assert snapshot.memory_percent == pytest.approx(62.5)
    assert snapshot.primary_gpu is not None
    assert snapshot.primary_gpu.name == "Test GPU"


def test_nvidia_smi_parser_reads_multiple_gpus() -> None:
    output = (
        "NVIDIA RTX A, 35, 1024, 8192\n"
        "NVIDIA RTX B, 82, 2048, 16384\n"
    )

    snapshots = NvidiaSmiGpuReader.parse_output(output)

    assert len(snapshots) == 2
    assert snapshots[0].utilization_percent == pytest.approx(35.0)
    assert snapshots[0].memory_used_bytes == 1024 * 1024 * 1024
    assert snapshots[1].utilization_percent == pytest.approx(82.0)


def test_system_resource_reader_handles_missing_gpu_backend() -> None:
    reader = SystemResourceReader(
        gpu_readers=(),
        psutil_module=_FakePsutil(),
    )

    snapshot = reader.snapshot()

    assert snapshot.gpus == ()
    assert "No supported GPU telemetry backend" in snapshot.gpu_status



def test_gpu_snapshot_supports_detection_only_telemetry() -> None:
    snapshot = GpuResourceSnapshot(
        name="Intel Iris Xe Graphics",
        backend="windows-cim",
        device_id="luid_0x00000000_0x00010850_phys_0",
        vendor="Intel",
    )

    assert snapshot.utilization_percent is None
    assert snapshot.has_utilization is False
    assert snapshot.has_memory_telemetry is False
    assert snapshot.telemetry_level == "detected"


def test_gpu_snapshot_supports_partial_windows_memory() -> None:
    snapshot = GpuResourceSnapshot(
        name="Intel Iris Xe Graphics",
        backend="windows-cim",
        device_id="luid_0x00000000_0x00010850_phys_0",
        vendor="Intel",
        dedicated_memory_used_bytes=0,
        shared_memory_used_bytes=1024**3,
        committed_memory_bytes=1536 * 1024**2,
    )

    assert snapshot.utilization_percent is None
    assert snapshot.has_memory_telemetry is True
    assert snapshot.telemetry_level == "partial"
    assert snapshot.shared_memory_used_bytes == 1024**3


def test_primary_gpu_prefers_measured_utilization() -> None:
    detected_only = GpuResourceSnapshot(
        name="Detected GPU",
        backend="detection",
    )
    measured_idle = GpuResourceSnapshot(
        name="Measured idle GPU",
        utilization_percent=0.0,
        backend="measured",
    )

    system_snapshot = SystemResourceSnapshot(
        captured_at=1.0,
        cpu_percent=0.0,
        per_core_percent=(0.0,),
        physical_cores=1,
        logical_cores=1,
        active_logical_cores=0,
        active_core_threshold_percent=5.0,
        memory_percent=0.0,
        memory_used_bytes=0,
        memory_total_bytes=1,
        gpus=(detected_only, measured_idle),
    )

    assert system_snapshot.primary_gpu is measured_idle


@pytest.mark.parametrize(
    "invalid_utilization",
    [-0.1, 100.1],
)
def test_gpu_snapshot_rejects_invalid_optional_utilization(
    invalid_utilization: float,
) -> None:
    with pytest.raises(ValueError):
        GpuResourceSnapshot(
            name="Invalid GPU",
            utilization_percent=invalid_utilization,
        )
