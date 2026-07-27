from __future__ import annotations

import json
from pathlib import Path

import pytest

from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.main_window import MainWindow


def _build_nested_gow_run(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    output_root = tmp_path / "gow-output"
    run_root = output_root / "runs" / "run-real"
    generation_root = run_root / "generation_000000"
    candidate_root = generation_root / "candidate_000001"
    candidate_root.mkdir(parents=True)

    payload = {
        "problem_id": "toy-sphere-de",
        "run_id": "run-real",
        "candidate_id": "candidate_000001",
        "attempt_id": "candidate_000001_a000",
        "fitness": {
            "status": "ok",
            "objective": 1.25,
        },
    }
    (candidate_root / "result.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return output_root, run_root, generation_root


@pytest.mark.parametrize(
    "selection_kind",
    ("output", "runs", "run", "generation"),
)
def test_reader_accepts_any_folder_inside_gow_tree(
    tmp_path: Path,
    selection_kind: str,
) -> None:
    output_root, run_root, generation_root = (
        _build_nested_gow_run(tmp_path)
    )
    selections = {
        "output": output_root,
        "runs": output_root / "runs",
        "run": run_root,
        "generation": generation_root,
    }

    reader = GowFilesystemRunReader(selections[selection_kind])
    references = reader.discover_runs()

    assert len(references) == 1
    assert references[0].run_id == "run-real"
    assert reader.snapshot_of(references[0]).evaluation_count == 1


def test_ui_loads_run_from_generation_folder(
    qtbot,
    tmp_path: Path,
) -> None:
    _output_root, _run_root, generation_root = (
        _build_nested_gow_run(tmp_path)
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.connect_results_root(generation_root)

    assert window.run_selector.count() == 1
    assert window.run_selector.currentData() == "run-real"
    assert window.current_snapshot is not None
    assert window.current_snapshot.evaluation_count == 1
    assert "run-real" in window.job_label.text()
