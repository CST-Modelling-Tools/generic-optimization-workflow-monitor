from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

from gow_monitor.infrastructure.process_resources import GowProcessTreeReader

GRANDCHILD_CODE = r"""
import math
import time

deadline = time.time() + 12.0
accumulator = 0.0

while time.time() < deadline:
    for index in range(1, 120000):
        accumulator += math.sqrt(index) * math.sin(index)

print(accumulator)
"""


def build_root_code() -> str:
    executable = str(Path(sys.executable).resolve())

    return f"""
import math
import subprocess
import time

child = subprocess.Popen(
    [
        {executable!r},
        "-c",
        {GRANDCHILD_CODE!r},
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

deadline = time.time() + 12.0
accumulator = 0.0

try:
    while time.time() < deadline:
        for index in range(1, 120000):
            accumulator += math.sqrt(index) * math.cos(index)
finally:
    try:
        child.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2.0)

print(accumulator)
"""


def terminate_process_tree(root_pid: int) -> None:
    try:
        root = psutil.Process(root_pid)
    except psutil.NoSuchProcess:
        return

    try:
        descendants = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []

    for process in reversed(descendants):
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    try:
        root.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    processes = [*descendants, root]
    _gone, alive = psutil.wait_procs(processes, timeout=3.0)

    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if alive:
        psutil.wait_procs(alive, timeout=3.0)


def main() -> int:
    print("=" * 88)
    print("REAL PROCESS TREE SMOKE TEST")
    print("=" * 88)
    print(f"Python executable: {sys.executable}")
    print(f"Logical cores: {psutil.cpu_count(logical=True)}")
    print()

    root_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            build_root_code(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    reader = GowProcessTreeReader(root_process.pid)

    maximum_process_count = 0
    maximum_thread_count = 0
    maximum_memory_bytes = 0
    maximum_cpu_process_percent = 0.0
    maximum_cpu_host_percent = 0.0
    observed_pids: set[int] = set()
    available_samples = 0

    try:
        # Dejamos tiempo para que el proceso raíz cree al descendiente.
        time.sleep(0.75)

        for sample_index in range(1, 9):
            snapshot = reader.snapshot()

            payload = {
                "sample": sample_index,
                "available": snapshot.available,
                "status": snapshot.status,
                "root_pid": snapshot.root_pid,
                "root_name": snapshot.root_name,
                "cpu_process_percent": snapshot.cpu_process_percent,
                "cpu_host_percent": snapshot.cpu_host_percent,
                "memory_rss_bytes": snapshot.memory_rss_bytes,
                "process_count": snapshot.process_count,
                "child_process_count": snapshot.child_process_count,
                "thread_count": snapshot.thread_count,
                "active_pids": snapshot.active_pids,
                "inaccessible_processes": snapshot.inaccessible_processes,
            }

            print(json.dumps(payload, ensure_ascii=False))

            if snapshot.available:
                available_samples += 1

                maximum_process_count = max(
                    maximum_process_count,
                    snapshot.process_count or 0,
                )
                maximum_thread_count = max(
                    maximum_thread_count,
                    snapshot.thread_count or 0,
                )
                maximum_memory_bytes = max(
                    maximum_memory_bytes,
                    snapshot.memory_rss_bytes or 0,
                )
                maximum_cpu_process_percent = max(
                    maximum_cpu_process_percent,
                    snapshot.cpu_process_percent or 0.0,
                )
                maximum_cpu_host_percent = max(
                    maximum_cpu_host_percent,
                    snapshot.cpu_host_percent or 0.0,
                )
                observed_pids.update(snapshot.active_pids)

            time.sleep(0.75)

    finally:
        terminate_process_tree(root_process.pid)

    summary = {
        "available_samples": available_samples,
        "maximum_process_count": maximum_process_count,
        "maximum_thread_count": maximum_thread_count,
        "maximum_memory_bytes": maximum_memory_bytes,
        "maximum_memory_mib": maximum_memory_bytes / (1024**2),
        "maximum_cpu_process_percent": maximum_cpu_process_percent,
        "maximum_cpu_host_percent": maximum_cpu_host_percent,
        "observed_pids": sorted(observed_pids),
    }

    print()
    print("=" * 88)
    print("SUMMARY")
    print("=" * 88)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()

    failures: list[str] = []

    if available_samples < 2:
        failures.append(
            "Fewer than two available telemetry samples were collected."
        )

    if maximum_process_count < 2:
        failures.append(
            "The recursive reader did not observe the root process and its child."
        )

    if len(observed_pids) < 2:
        failures.append(
            "Fewer than two real process identifiers were observed."
        )

    if maximum_thread_count < 2:
        failures.append(
            "The aggregated process tree reported fewer than two threads."
        )

    if maximum_memory_bytes <= 0:
        failures.append(
            "The aggregated RSS memory value was not positive."
        )

    if maximum_cpu_process_percent <= 0.0:
        failures.append(
            "No positive process CPU utilization was observed."
        )

    if maximum_cpu_host_percent <= 0.0:
        failures.append(
            "No positive host-normalized GOW CPU utilization was observed."
        )

    if failures:
        print("SMOKE TEST FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("SMOKE TEST PASSED")
    print(
        "The process reader observed and aggregated a real recursive "
        "Windows process tree."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
