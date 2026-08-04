from __future__ import annotations

import json

import pytest

from gow_monitor.domain import GpuResourceSnapshot
from gow_monitor.infrastructure.gpu_resources import (
    GpuReaderRegistry,
    NvidiaSmiGpuReader,
    WindowsCimGpuReader,
)


def _windows_payload() -> str:
    return json.dumps(
        {
            "engines": [
                {
                    "name": (
                        "pid_1_luid_0x00000000_0x00010850_phys_0_"
                        "eng_0_engtype_3D"
                    ),
                    "utilization": 20,
                },
                {
                    "name": (
                        "pid_2_luid_0x00000000_0x00010850_phys_0_"
                        "eng_0_engtype_3D"
                    ),
                    "utilization": 15,
                },
                {
                    "name": (
                        "pid_3_luid_0x00000000_0x00010850_phys_0_"
                        "eng_2_engtype_Copy"
                    ),
                    "utilization": 70,
                },
                {
                    "name": (
                        "pid_4_luid_0x00000000_0x00010BD0_phys_0_"
                        "eng_0_engtype_3D"
                    ),
                    "utilization": 5,
                },
            ],
            "memory": [
                {
                    "name": (
                        "luid_0x00000000_0x00010850_phys_0"
                    ),
                    "dedicated": 0,
                    "shared": 1024**3,
                    "committed": 1536 * 1024**2,
                },
                {
                    "name": (
                        "luid_0x00000000_0x00010BD0_phys_0"
                    ),
                    "dedicated": 0,
                    "shared": 8192,
                    "committed": 212992,
                },
            ],
            "controllers": [
                {
                    "name": "Intel(R) Iris(R) Xe Graphics",
                    "vendor": "Intel Corporation",
                    "pnp_device_id": "PCI\\VEN_8086&DEV_9A49",
                    "status": "OK",
                }
            ],
        }
    )


def test_windows_cim_parser_aggregates_per_engine() -> None:
    snapshots = WindowsCimGpuReader.parse_output(
        _windows_payload()
    )

    assert len(snapshots) == 2

    primary = snapshots[0]
    assert primary.name == "Intel(R) Iris(R) Xe Graphics"
    assert primary.vendor == "Intel"
    assert primary.device_id == (
        "luid_0x00000000_0x00010850_phys_0"
    )

    # 3D totals 35%, Copy totals 70%; overall is the busiest engine.
    assert primary.utilization_percent == pytest.approx(70.0)
    assert primary.shared_memory_used_bytes == 1024**3
    assert primary.committed_memory_bytes == 1536 * 1024**2


def test_windows_cim_parser_does_not_sum_different_engines() -> None:
    primary = WindowsCimGpuReader.parse_output(
        _windows_payload()
    )[0]

    assert primary.utilization_percent != pytest.approx(105.0)
    assert primary.utilization_percent == pytest.approx(70.0)


def test_windows_cim_parser_preserves_secondary_luid() -> None:
    snapshots = WindowsCimGpuReader.parse_output(
        _windows_payload()
    )

    secondary = snapshots[1]

    assert secondary.name == "Windows GPU adapter 2"
    assert secondary.device_id == (
        "luid_0x00000000_0x00010bd0_phys_0"
    )
    assert secondary.utilization_percent == pytest.approx(5.0)


def test_windows_cim_supports_detection_only_controller() -> None:
    output = json.dumps(
        {
            "engines": [],
            "memory": [],
            "controllers": [
                {
                    "name": "Intel Iris Xe Graphics",
                    "vendor": "Intel Corporation",
                    "pnp_device_id": "PCI\\VEN_8086",
                    "status": "OK",
                }
            ],
        }
    )

    snapshot = WindowsCimGpuReader.parse_output(output)[0]

    assert snapshot.name == "Intel Iris Xe Graphics"
    assert snapshot.utilization_percent is None
    assert snapshot.telemetry_level == "detected"


class _StaticGpuReader:
    is_available = True

    def __init__(
        self,
        backend_name: str,
        snapshots: tuple[GpuResourceSnapshot, ...],
    ) -> None:
        self.backend_name = backend_name
        self._snapshots = snapshots

    def read(self) -> tuple[GpuResourceSnapshot, ...]:
        return self._snapshots


def test_registry_merges_vendor_and_windows_samples() -> None:
    vendor = GpuResourceSnapshot(
        name="NVIDIA GeForce RTX Test",
        utilization_percent=40.0,
        memory_used_bytes=2 * 1024**3,
        memory_total_bytes=8 * 1024**3,
        backend="nvidia-smi",
        device_id="GPU-TEST",
        vendor="NVIDIA",
    )

    windows = GpuResourceSnapshot(
        name="NVIDIA GeForce RTX Test",
        utilization_percent=35.0,
        backend="windows-cim",
        device_id="luid_test",
        vendor="NVIDIA",
        dedicated_memory_used_bytes=512 * 1024**2,
        committed_memory_bytes=3 * 1024**3,
    )

    registry = GpuReaderRegistry(
        (
            _StaticGpuReader("nvidia-smi", (vendor,)),
            _StaticGpuReader("windows-cim", (windows,)),
        )
    )

    snapshots, status = registry.read()

    assert len(snapshots) == 1
    assert snapshots[0].utilization_percent == pytest.approx(40.0)
    assert snapshots[0].memory_total_bytes == 8 * 1024**3
    assert snapshots[0].dedicated_memory_used_bytes == 512 * 1024**2
    assert snapshots[0].backend == "nvidia-smi+windows-cim"
    assert "nvidia-smi + windows-cim" in status


def test_nvidia_parser_accepts_uuid_output() -> None:
    output = (
        "GPU-1234, NVIDIA RTX Test, 52, 1024, 8192\n"
    )

    snapshot = NvidiaSmiGpuReader.parse_output(output)[0]

    assert snapshot.device_id == "GPU-1234"
    assert snapshot.vendor == "NVIDIA"
    assert snapshot.utilization_percent == pytest.approx(52.0)
