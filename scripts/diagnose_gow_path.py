from __future__ import annotations

import argparse
import json
from pathlib import Path

from gow_monitor.infrastructure import GowFilesystemRunReader


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect how GOW Monitor resolves a selected path."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    reader = GowFilesystemRunReader(args.path)
    print(json.dumps(reader.diagnostics(), indent=2, ensure_ascii=False))

    for reference in reader.discover_runs():
        snapshot = reader.snapshot_of(reference)
        print()
        print(f"RUN: {reference.run_id}")
        print(f"ROOT: {reference.run_root}")
        print(f"PROBLEM: {reference.problem_id or 'unknown'}")
        print(f"DIRECTION: {reference.direction.value}")
        print(f"STATE: {snapshot.state.value}")
        print(f"EVALUATIONS: {snapshot.evaluation_count}")
        print(f"FAILURES: {snapshot.failed_evaluations}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
