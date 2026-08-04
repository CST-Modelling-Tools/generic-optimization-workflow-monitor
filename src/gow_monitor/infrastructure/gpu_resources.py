from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from gow_monitor.domain import GpuResourceSnapshot

MIB = 1024 * 1024

_DEVICE_PATTERN = re.compile(
    r"(luid_0x[0-9a-f]+_0x[0-9a-f]+_phys_\d+)",
    re.IGNORECASE,
)
_ENGINE_PATTERN = re.compile(
    r"_eng_(\d+)_engtype_(.*)$",
    re.IGNORECASE,
)


class GpuReader(Protocol):
    @property
    def backend_name(self) -> str:
        ...

    @property
    def is_available(self) -> bool:
        ...

    def read(self) -> tuple[GpuResourceSnapshot, ...]:
        ...


class NvidiaSmiGpuReader:
    """Read NVIDIA device telemetry through nvidia-smi."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_s: float = 2.0,
        runner: Any = subprocess.run,
    ) -> None:
        self._executable = executable or shutil.which("nvidia-smi")
        self._timeout_s = timeout_s
        self._runner = runner

    @property
    def backend_name(self) -> str:
        return "nvidia-smi"

    @property
    def is_available(self) -> bool:
        return bool(self._executable)

    def read(self) -> tuple[GpuResourceSnapshot, ...]:
        if not self._executable:
            return ()

        completed = self._runner(
            [
                self._executable,
                (
                    "--query-gpu="
                    "uuid,name,utilization.gpu,memory.used,memory.total"
                ),
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._timeout_s,
        )

        return self.parse_output(completed.stdout)

    @staticmethod
    def parse_output(output: str) -> tuple[GpuResourceSnapshot, ...]:
        snapshots: list[GpuResourceSnapshot] = []

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            fields = [field.strip() for field in line.split(",")]

            if len(fields) == 5:
                (
                    device_id,
                    name,
                    utilization_raw,
                    used_raw,
                    total_raw,
                ) = fields
            elif len(fields) == 4:
                device_id = ""
                (
                    name,
                    utilization_raw,
                    used_raw,
                    total_raw,
                ) = fields
            else:
                continue

            utilization = _optional_float(utilization_raw)
            used_mib = _optional_float(used_raw)
            total_mib = _optional_float(total_raw)

            used_bytes = (
                max(0, int(used_mib * MIB))
                if used_mib is not None
                else None
            )
            total_bytes = (
                max(0, int(total_mib * MIB))
                if total_mib is not None
                else None
            )

            if (
                used_bytes is not None
                and total_bytes is not None
                and used_bytes > total_bytes
            ):
                used_bytes = total_bytes

            snapshots.append(
                GpuResourceSnapshot(
                    name=name or "NVIDIA GPU",
                    utilization_percent=(
                        min(100.0, max(0.0, utilization))
                        if utilization is not None
                        else None
                    ),
                    memory_used_bytes=used_bytes,
                    memory_total_bytes=total_bytes,
                    backend="nvidia-smi",
                    device_id=device_id or None,
                    vendor="NVIDIA",
                )
            )

        return tuple(snapshots)


class WindowsCimGpuReader:
    """Read vendor-neutral Windows GPU performance counters through CIM."""

    POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$engines = @(
    try {
        Get-CimInstance `
            -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine |
            ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.Name
                    utilization = [double]$_.UtilizationPercentage
                }
            }
    }
    catch {
        @()
    }
)

$memory = @(
    try {
        Get-CimInstance `
            -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory |
            ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.Name
                    dedicated = [uint64]$_.DedicatedUsage
                    shared = [uint64]$_.SharedUsage
                    committed = [uint64]$_.TotalCommitted
                }
            }
    }
    catch {
        @()
    }
)

$controllers = @(
    try {
        Get-CimInstance -ClassName Win32_VideoController |
            ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.Name
                    vendor = [string]$_.AdapterCompatibility
                    pnp_device_id = [string]$_.PNPDeviceID
                    status = [string]$_.Status
                }
            }
    }
    catch {
        @()
    }
)

[pscustomobject]@{
    engines = $engines
    memory = $memory
    controllers = $controllers
} | ConvertTo-Json -Depth 6 -Compress
"""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_s: float = 5.0,
        platform_name: str | None = None,
        runner: Any = subprocess.run,
    ) -> None:
        self._platform_name = platform_name or platform.system()
        self._executable = executable or (
            shutil.which("powershell")
            or shutil.which("powershell.exe")
            or shutil.which("pwsh")
        )
        self._timeout_s = timeout_s
        self._runner = runner

    @property
    def backend_name(self) -> str:
        return "windows-cim"

    @property
    def is_available(self) -> bool:
        return (
            self._platform_name.lower() == "windows"
            and bool(self._executable)
        )

    def read(self) -> tuple[GpuResourceSnapshot, ...]:
        if not self.is_available or not self._executable:
            return ()

        completed = self._runner(
            [
                self._executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                self.POWERSHELL_SCRIPT,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._timeout_s,
        )

        return self.parse_output(completed.stdout)

    @classmethod
    def parse_output(
        cls,
        output: str,
    ) -> tuple[GpuResourceSnapshot, ...]:
        cleaned = output.strip().lstrip("\ufeff")
        if not cleaned:
            return ()

        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Windows GPU CIM output must be a JSON object")

        engines = _as_list(payload.get("engines"))
        memories = _as_list(payload.get("memory"))
        controllers = _as_list(payload.get("controllers"))

        engine_totals: dict[tuple[str, str], float] = {}

        for index, raw_engine in enumerate(engines):
            if not isinstance(raw_engine, dict):
                continue

            instance_name = str(raw_engine.get("name") or "")
            device_id = cls._device_id(instance_name)
            if device_id is None:
                continue

            utilization = _optional_float(raw_engine.get("utilization"))
            if utilization is None:
                continue

            engine_match = _ENGINE_PATTERN.search(instance_name)
            if engine_match is None:
                engine_key = f"unknown-{index}"
            else:
                engine_number = engine_match.group(1)
                engine_type = engine_match.group(2).strip()
                engine_key = engine_type or f"engine-{engine_number}"

            key = (device_id, engine_key.lower())
            engine_totals[key] = (
                engine_totals.get(key, 0.0)
                + max(0.0, utilization)
            )

        utilization_by_device: dict[str, float] = {}

        for (device_id, _engine_key), utilization in engine_totals.items():
            bounded = min(100.0, utilization)
            previous = utilization_by_device.get(device_id)

            if previous is None or bounded > previous:
                utilization_by_device[device_id] = bounded

        memory_by_device: dict[str, dict[str, int | None]] = {}

        for raw_memory in memories:
            if not isinstance(raw_memory, dict):
                continue

            instance_name = str(raw_memory.get("name") or "")
            device_id = cls._device_id(instance_name)
            if device_id is None:
                continue

            memory_by_device[device_id] = {
                "dedicated": _optional_int(raw_memory.get("dedicated")),
                "shared": _optional_int(raw_memory.get("shared")),
                "committed": _optional_int(raw_memory.get("committed")),
            }

        device_ids = set(utilization_by_device)
        device_ids.update(memory_by_device)

        parsed_controllers = tuple(
            controller
            for controller in controllers
            if isinstance(controller, dict)
            and str(controller.get("name") or "").strip()
        )

        if not device_ids:
            return cls._controller_only_snapshots(parsed_controllers)

        controller_by_device: dict[str, dict[str, Any]] = {}

        if len(parsed_controllers) == 1:
            dominant_device = max(
                device_ids,
                key=lambda device_id: cls._device_score(
                    device_id,
                    utilization_by_device,
                    memory_by_device,
                ),
            )
            controller_by_device[dominant_device] = parsed_controllers[0]

        ordered_device_ids = sorted(
            device_ids,
            key=lambda device_id: cls._device_score(
                device_id,
                utilization_by_device,
                memory_by_device,
            ),
            reverse=True,
        )

        snapshots: list[GpuResourceSnapshot] = []

        for index, device_id in enumerate(ordered_device_ids):
            controller = controller_by_device.get(device_id)
            memory = memory_by_device.get(device_id, {})

            if controller is None:
                name = f"Windows GPU adapter {index + 1}"
                vendor = None
            else:
                name = str(controller.get("name") or "").strip()
                vendor = _normalize_vendor(
                    controller.get("vendor")
                )

            snapshots.append(
                GpuResourceSnapshot(
                    name=name,
                    utilization_percent=utilization_by_device.get(
                        device_id
                    ),
                    backend="windows-cim",
                    device_id=device_id,
                    vendor=vendor,
                    dedicated_memory_used_bytes=memory.get(
                        "dedicated"
                    ),
                    shared_memory_used_bytes=memory.get("shared"),
                    committed_memory_bytes=memory.get("committed"),
                )
            )

        return tuple(snapshots)

    @staticmethod
    def _device_id(instance_name: str) -> str | None:
        match = _DEVICE_PATTERN.search(instance_name)
        if match is None:
            return None
        return match.group(1).lower()

    @staticmethod
    def _device_score(
        device_id: str,
        utilization_by_device: dict[str, float],
        memory_by_device: dict[str, dict[str, int | None]],
    ) -> tuple[int, int, float, str]:
        memory = memory_by_device.get(device_id, {})

        committed = memory.get("committed")
        shared = memory.get("shared")
        dedicated = memory.get("dedicated")

        committed_value = int(committed or 0)
        observed_memory = int(shared or 0) + int(dedicated or 0)
        utilization = utilization_by_device.get(device_id, -1.0)

        return (
            committed_value,
            observed_memory,
            utilization,
            device_id,
        )

    @staticmethod
    def _controller_only_snapshots(
        controllers: tuple[dict[str, Any], ...],
    ) -> tuple[GpuResourceSnapshot, ...]:
        snapshots: list[GpuResourceSnapshot] = []

        for index, controller in enumerate(controllers):
            name = str(controller.get("name") or "").strip()
            pnp_device_id = str(
                controller.get("pnp_device_id") or ""
            ).strip()

            snapshots.append(
                GpuResourceSnapshot(
                    name=name,
                    backend="windows-cim",
                    device_id=(
                        pnp_device_id
                        or f"windows-video-controller-{index}"
                    ),
                    vendor=_normalize_vendor(
                        controller.get("vendor")
                    ),
                )
            )

        return tuple(snapshots)


class GpuReaderRegistry:
    """Read and combine multiple GPU telemetry backends."""

    def __init__(
        self,
        readers: Sequence[GpuReader],
        *,
        platform_name: str | None = None,
    ) -> None:
        self._readers = tuple(readers)
        self._platform_name = platform_name or platform.system()

    @property
    def readers(self) -> tuple[GpuReader, ...]:
        return self._readers

    @property
    def available_readers(self) -> tuple[GpuReader, ...]:
        return tuple(
            reader
            for reader in self._readers
            if reader.is_available
        )

    def read(
        self,
    ) -> tuple[tuple[GpuResourceSnapshot, ...], str]:
        available = self.available_readers

        if not available:
            return (), (
                "No supported GPU telemetry backend detected on "
                f"{self._platform_name or 'this platform'}"
            )

        collected: list[GpuResourceSnapshot] = []
        successful_backends: list[str] = []
        errors: list[str] = []

        for reader in available:
            try:
                snapshots = reader.read()
            except (
                OSError,
                subprocess.SubprocessError,
                ValueError,
            ) as exc:
                errors.append(f"{reader.backend_name}: {exc}")
                continue

            if snapshots:
                collected.extend(snapshots)
                successful_backends.append(reader.backend_name)

        merged = self._merge_snapshots(collected)

        if merged:
            providers = " + ".join(
                dict.fromkeys(successful_backends)
            )
            return (
                merged,
                f"GPU telemetry provided by {providers}",
            )

        if errors:
            return (), "; ".join(errors)

        return (), (
            "GPU backend detected, but no GPU samples were returned"
        )

    @classmethod
    def _merge_snapshots(
        cls,
        snapshots: Sequence[GpuResourceSnapshot],
    ) -> tuple[GpuResourceSnapshot, ...]:
        merged: list[GpuResourceSnapshot] = []

        for snapshot in snapshots:
            matching_index = cls._matching_index(
                merged,
                snapshot,
            )

            if matching_index is None:
                merged.append(snapshot)
                continue

            merged[matching_index] = cls._merge_two(
                merged[matching_index],
                snapshot,
            )

        return tuple(merged)

    @classmethod
    def _matching_index(
        cls,
        existing: Sequence[GpuResourceSnapshot],
        candidate: GpuResourceSnapshot,
    ) -> int | None:
        candidate_name = cls._normalized_name(candidate.name)

        for index, current in enumerate(existing):
            if (
                current.device_id is not None
                and candidate.device_id is not None
                and current.device_id == candidate.device_id
            ):
                return index

            current_name = cls._normalized_name(current.name)

            if (
                candidate_name
                and candidate_name == current_name
                and not cls._generic_name(candidate.name)
                and not cls._generic_name(current.name)
            ):
                return index

        return None

    @classmethod
    def _merge_two(
        cls,
        primary: GpuResourceSnapshot,
        secondary: GpuResourceSnapshot,
    ) -> GpuResourceSnapshot:
        name = primary.name

        if (
            cls._generic_name(primary.name)
            and not cls._generic_name(secondary.name)
        ):
            name = secondary.name

        backend = primary.backend
        if secondary.backend != primary.backend:
            backend = f"{primary.backend}+{secondary.backend}"

        return replace(
            primary,
            name=name,
            utilization_percent=(
                primary.utilization_percent
                if primary.utilization_percent is not None
                else secondary.utilization_percent
            ),
            memory_used_bytes=(
                primary.memory_used_bytes
                if primary.memory_used_bytes is not None
                else secondary.memory_used_bytes
            ),
            memory_total_bytes=(
                primary.memory_total_bytes
                if primary.memory_total_bytes is not None
                else secondary.memory_total_bytes
            ),
            backend=backend,
            device_id=primary.device_id or secondary.device_id,
            vendor=primary.vendor or secondary.vendor,
            dedicated_memory_used_bytes=(
                primary.dedicated_memory_used_bytes
                if primary.dedicated_memory_used_bytes is not None
                else secondary.dedicated_memory_used_bytes
            ),
            shared_memory_used_bytes=(
                primary.shared_memory_used_bytes
                if primary.shared_memory_used_bytes is not None
                else secondary.shared_memory_used_bytes
            ),
            committed_memory_bytes=(
                primary.committed_memory_bytes
                if primary.committed_memory_bytes is not None
                else secondary.committed_memory_bytes
            ),
        )

    @staticmethod
    def _normalized_name(name: str) -> str:
        normalized = name.lower()
        normalized = normalized.replace("(r)", "")
        normalized = normalized.replace("(tm)", "")
        return re.sub(r"[^a-z0-9]+", "", normalized)

    @staticmethod
    def _generic_name(name: str) -> bool:
        lowered = name.strip().lower()
        return lowered.startswith("windows gpu adapter")


def default_gpu_readers(
    *,
    platform_name: str | None = None,
) -> tuple[GpuReader, ...]:
    current_platform = platform_name or platform.system()

    readers: list[GpuReader] = [
        NvidiaSmiGpuReader(),
    ]

    if current_platform.lower() == "windows":
        readers.append(
            WindowsCimGpuReader(
                platform_name=current_platform,
            )
        )

    return tuple(readers)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.lower() in {
        "n/a",
        "na",
        "not supported",
        "[not supported]",
    }:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return max(0, int(number))


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_vendor(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    lowered = raw.lower()

    if "intel" in lowered:
        return "Intel"
    if "nvidia" in lowered:
        return "NVIDIA"
    if "advanced micro devices" in lowered or "amd" in lowered:
        return "AMD"
    if "apple" in lowered:
        return "Apple"
    if "microsoft" in lowered:
        return "Microsoft"

    return raw
