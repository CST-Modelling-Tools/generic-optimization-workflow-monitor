from __future__ import annotations

import argparse
import gc
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from gow_monitor.infrastructure import (
    GowFilesystemRunReader,
    GowProcessTreeReader,
    SystemResourceReader,
)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _touch_allocation(size_mib: int) -> bytearray:
    payload = bytearray(max(0, size_mib) * 1024 * 1024)
    for index in range(0, len(payload), 4096):
        payload[index] = 1
    return payload


def _worker(
    *,
    outdir: Path,
    run_id: str,
    evaluations: int,
    batch_size: int,
    memory_mib: int,
    pulse_mib: int,
    generation_delay_s: float,
) -> int:
    run_root = outdir / "runs" / run_id
    generation_root = run_root / "generations"
    generation_root.mkdir(parents=True, exist_ok=True)

    base_memory = _touch_allocation(memory_mib)
    pulse_memory: bytearray | None = None

    generation_count = math.ceil(evaluations / batch_size)
    completed = 0

    _atomic_json(
        run_root / "summary.json",
        {
            "problem_id": "monitor-resource-stress",
            "run_id": run_id,
            "max_evaluations": evaluations,
            "evaluations_done": 0,
            "completed_generations": 0,
            "finalized": False,
            "objective": {"direction": "minimize"},
        },
    )

    for generation in range(generation_count):
        generation_start = completed
        generation_stop = min(
            evaluations,
            generation_start + batch_size,
        )
        shard_path = (
            generation_root / f"g{generation:06d}.jsonl"
        )
        temporary = shard_path.with_suffix(".jsonl.tmp")

        started_at = _utc_now()
        with temporary.open("w", encoding="utf-8") as handle:
            for candidate_index in range(
                generation_start,
                generation_stop,
            ):
                x = (
                    (candidate_index % 2001) - 1000
                ) / 1000.0
                y = (
                    ((candidate_index * 17) % 2001) - 1000
                ) / 1000.0
                objective = x * x + y * y
                candidate_id = (
                    f"stress_g{generation:06d}_"
                    f"c{candidate_index:09d}"
                )
                record = {
                    "problem_id": "monitor-resource-stress",
                    "run_id": run_id,
                    "generation_id": generation,
                    "candidate_index": candidate_index,
                    "candidate_id": candidate_id,
                    "candidate_local_id": (
                        f"g{generation:06d}_"
                        f"c{candidate_index:09d}"
                    ),
                    "attempt_id": f"{candidate_id}_a000",
                    "attempt_index": 0,
                    "params": {"x": x, "y": y},
                    "fitness": {
                        "status": "ok",
                        "objective": objective,
                    },
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                }
                handle.write(
                    json.dumps(record, separators=(",", ":"))
                    + "\n"
                )

        os.replace(temporary, shard_path)
        completed = generation_stop

        if generation % 2 == 0:
            pulse_memory = _touch_allocation(pulse_mib)
        else:
            pulse_memory = None
            gc.collect()

        _atomic_json(
            run_root / "summary.json",
            {
                "problem_id": "monitor-resource-stress",
                "run_id": run_id,
                "max_evaluations": evaluations,
                "evaluations_done": completed,
                "completed_generations": generation + 1,
                "finalized": completed >= evaluations,
                "objective": {"direction": "minimize"},
            },
        )

        print(
            f"[producer] generation={generation + 1}/"
            f"{generation_count} evaluations={completed}/"
            f"{evaluations}",
            flush=True,
        )
        time.sleep(generation_delay_s)

    del pulse_memory
    del base_memory
    gc.collect()
    time.sleep(1.5)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stress GOW Monitor with a large GOW-compatible artifact run "
            "and controlled RAM changes."
        )
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=(
            Path(tempfile.gettempdir())
            / "gow_monitor_resource_stress"
        ),
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--evaluations", type=int, default=50_000)
    parser.add_argument("--batch-size", type=int, default=2_500)
    parser.add_argument("--memory-mib", type=int, default=256)
    parser.add_argument("--pulse-mib", type=int, default=128)
    parser.add_argument("--generation-delay-ms", type=int, default=600)
    parser.add_argument("--sample-interval-ms", type=int, default=500)
    parser.add_argument("--no-launch-monitor", action="store_true")
    parser.add_argument("--worker", action="store_true")
    return parser


def _validate_arguments(arguments: argparse.Namespace) -> None:
    if arguments.evaluations < 1:
        raise ValueError("--evaluations must be positive")
    if arguments.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    if arguments.memory_mib < 0:
        raise ValueError("--memory-mib cannot be negative")
    if arguments.pulse_mib < 0:
        raise ValueError("--pulse-mib cannot be negative")
    if arguments.generation_delay_ms < 0:
        raise ValueError("--generation-delay-ms cannot be negative")
    if arguments.sample_interval_ms < 100:
        raise ValueError("--sample-interval-ms must be at least 100")


def main() -> int:
    arguments = _build_parser().parse_args()
    _validate_arguments(arguments)

    outdir = arguments.outdir.expanduser().resolve()
    run_id = arguments.run_id or (
        "resource-stress-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
    )

    if arguments.worker:
        return _worker(
            outdir=outdir,
            run_id=run_id,
            evaluations=arguments.evaluations,
            batch_size=arguments.batch_size,
            memory_mib=arguments.memory_mib,
            pulse_mib=arguments.pulse_mib,
            generation_delay_s=(
                arguments.generation_delay_ms / 1000.0
            ),
        )

    outdir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()

    worker_command = [
        sys.executable,
        str(script_path),
        "--worker",
        "--outdir",
        str(outdir),
        "--run-id",
        run_id,
        "--evaluations",
        str(arguments.evaluations),
        "--batch-size",
        str(arguments.batch_size),
        "--memory-mib",
        str(arguments.memory_mib),
        "--pulse-mib",
        str(arguments.pulse_mib),
        "--generation-delay-ms",
        str(arguments.generation_delay_ms),
        "--sample-interval-ms",
        str(arguments.sample_interval_ms),
        "--no-launch-monitor",
    ]

    worker = subprocess.Popen(worker_command, text=True)
    print(f"Stress producer PID: {worker.pid}")
    print(f"Output directory: {outdir}")
    print(f"Run ID: {run_id}")
    print(f"Target evaluations: {arguments.evaluations:,}")

    monitor: subprocess.Popen[str] | None = None
    if not arguments.no_launch_monitor:
        monitor = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gow_monitor",
                "--results-root",
                str(outdir),
                "--gow-pid",
                str(worker.pid),
            ],
            cwd=Path.cwd(),
            text=True,
        )
        print(f"GOW Monitor PID: {monitor.pid}")

    host_reader = SystemResourceReader(gpu_readers=())
    gow_reader = GowProcessTreeReader(worker.pid)

    host_samples = 0
    gow_available_samples = 0
    host_memory_values: list[int] = []
    gow_memory_values: list[int] = []
    artifact_source_counts: list[int] = []

    sample_interval = arguments.sample_interval_ms / 1000.0

    while worker.poll() is None:
        host = host_reader.snapshot()
        gow = gow_reader.snapshot()

        host_samples += 1
        host_memory_values.append(host.memory_used_bytes)

        if gow.available and gow.memory_rss_bytes is not None:
            gow_available_samples += 1
            gow_memory_values.append(gow.memory_rss_bytes)

        generation_root = outdir / "runs" / run_id / "generations"
        artifact_sources = (
            len(tuple(generation_root.glob("g*.jsonl")))
            if generation_root.is_dir()
            else 0
        )
        artifact_source_counts.append(artifact_sources)

        gow_rss_mib = (
            gow.memory_rss_bytes / 1024**2
            if gow.available and gow.memory_rss_bytes is not None
            else 0.0
        )
        print(
            "[telemetry] "
            f"host_ram={host.memory_percent:.2f}% "
            f"gow_rss={gow_rss_mib:.2f} MiB "
            f"artifact_sources={artifact_sources}",
            flush=True,
        )
        time.sleep(sample_interval)

    worker_return_code = worker.wait()
    time.sleep(0.5)

    reader = GowFilesystemRunReader(outdir)
    references = tuple(
        reference
        for reference in reader.discover_runs()
        if reference.run_id == run_id
    )

    failures: list[str] = []

    if worker_return_code != 0:
        failures.append(f"producer returned {worker_return_code}")

    if not references:
        failures.append("stress run was not discovered")
        final_snapshot = None
    else:
        final_snapshot = reader.snapshot_of(references[0])

    if host_samples < 3:
        failures.append(
            f"only {host_samples} host RAM samples were collected"
        )

    if not host_memory_values or min(host_memory_values) <= 0:
        failures.append("host RAM telemetry was unavailable")

    if gow_available_samples < 3:
        failures.append(
            "GOW RAM telemetry did not produce at least three available samples"
        )

    minimum_expected_rss = max(
        16 * 1024**2,
        int(arguments.memory_mib * 0.60 * 1024**2),
    )
    if (
        not gow_memory_values
        or max(gow_memory_values) < minimum_expected_rss
    ):
        failures.append(
            "GOW RAM did not observe the controlled allocation"
        )

    expected_sources = math.ceil(
        arguments.evaluations / arguments.batch_size
    )
    if (
        not artifact_source_counts
        or max(artifact_source_counts) < expected_sources
    ):
        failures.append(
            "Artifact sources did not reach the expected shard count"
        )

    if final_snapshot is not None:
        if final_snapshot.evaluation_count != arguments.evaluations:
            failures.append(
                "Final evaluation count mismatch: "
                f"{final_snapshot.evaluation_count} != "
                f"{arguments.evaluations}"
            )
        if final_snapshot.result_sources != expected_sources:
            failures.append(
                "Final artifact-source count mismatch: "
                f"{final_snapshot.result_sources} != {expected_sources}"
            )

    print("")
    print("=== RESOURCE STRESS SUMMARY ===")
    print(f"Host samples: {host_samples}")
    print(f"GOW RAM samples: {gow_available_samples}")
    print(
        "GOW RSS range: "
        f"{min(gow_memory_values, default=0) / 1024**2:.2f} - "
        f"{max(gow_memory_values, default=0) / 1024**2:.2f} MiB"
    )
    print(
        "Artifact sources observed: "
        f"{max(artifact_source_counts, default=0)} / {expected_sources}"
    )
    print(
        "Final evaluations: "
        f"{final_snapshot.evaluation_count if final_snapshot else 0:,} / "
        f"{arguments.evaluations:,}"
    )

    if failures:
        print("")
        print("RESOURCE STRESS TEST FAILED")
        for failure in failures:
            print(f" - {failure}")
        return 2

    print("")
    print("RESOURCE STRESS TEST PASSED")
    print(
        "Host RAM, GOW RSS, artifact-source growth and the final "
        "large evaluation count were all observed correctly."
    )
    if monitor is not None:
        print("GOW Monitor remains open for visual inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
