from __future__ import annotations

import time

from gow_monitor.infrastructure import WindowsCimGpuReader


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"

    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")

    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0

    return f"{size:.1f} TiB"


def main() -> int:
    reader = WindowsCimGpuReader()

    print("Windows CIM GPU reader smoke test")
    print(f"Backend available: {reader.is_available}")

    if not reader.is_available:
        print("SMOKE TEST FAILED: Windows CIM backend unavailable")
        return 2

    successful_samples = 0

    for sample_number in range(1, 4):
        snapshots = reader.read()

        print("")
        print(f"Sample {sample_number}: {len(snapshots)} GPU adapter(s)")

        if snapshots:
            successful_samples += 1

        for index, snapshot in enumerate(snapshots, start=1):
            utilization = (
                f"{snapshot.utilization_percent:.1f}%"
                if snapshot.utilization_percent is not None
                else "N/A"
            )

            print(f"  GPU {index}: {snapshot.name}")
            print(f"    vendor: {snapshot.vendor or 'N/A'}")
            print(f"    device_id: {snapshot.device_id or 'N/A'}")
            print(f"    utilization: {utilization}")
            dedicated_used = format_bytes(
                snapshot.dedicated_memory_used_bytes
            )
            print(
                f"    dedicated used: {dedicated_used}"
            )
            shared_used = format_bytes(
                snapshot.shared_memory_used_bytes
            )
            print(
                f"    shared used: {shared_used}"
            )
            committed = format_bytes(
                snapshot.committed_memory_bytes
            )
            print(
                f"    committed: {committed}"
            )
            print(
                f"    telemetry level: {snapshot.telemetry_level}"
            )

        time.sleep(1.0)

    if successful_samples != 3:
        print("")
        print(
            "SMOKE TEST FAILED: "
            f"{successful_samples}/3 successful samples"
        )
        return 3

    print("")
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
