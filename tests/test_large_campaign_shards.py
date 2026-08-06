from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.pages import OverviewPage


def _prepare_run(
    tmp_path: Path,
    *,
    shards: int,
) -> tuple[Path, Path]:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "large-run"
    generations = run_root / "generations"
    generations.mkdir(parents=True)

    for generation in range(shards):
        (generations / f"g{generation:06d}.jsonl").write_text(
            "",
            encoding="utf-8",
        )

    (run_root / "summary.json").write_text(
        json.dumps(
            {
                "problem_id": "large-campaign",
                "run_id": "large-run",
                "max_evaluations": 500_000,
                "evaluations_done": 500_000,
                "completed_generations": shards,
                "finalized": True,
                "objective": {"direction": "minimize"},
            }
        ),
        encoding="utf-8",
    )
    return results_root, run_root


def test_reader_counts_500k_records_across_generation_shards(
    monkeypatch,
    tmp_path: Path,
) -> None:
    results_root, _run_root = _prepare_run(
        tmp_path,
        shards=25,
    )
    calls = 0

    def fake_read_jsonl(
        path: Path,
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        nonlocal calls
        calls += 1
        generation = int(path.stem[1:])
        base = generation * 20_000
        for offset in range(20_000):
            candidate_index = base + offset
            candidate_id = (
                f"large_g{generation:06d}_c{candidate_index:06d}"
            )
            yield (
                offset + 1,
                {
                    "run_id": "large-run",
                    "problem_id": "large-campaign",
                    "generation_id": generation,
                    "candidate_index": candidate_index,
                    "candidate_id": candidate_id,
                    "attempt_id": f"{candidate_id}_a000",
                    "fitness": {
                        "status": "ok",
                        "objective": float(500_000 - candidate_index),
                    },
                },
            )

    monkeypatch.setattr(
        GowFilesystemRunReader,
        "_read_jsonl",
        staticmethod(fake_read_jsonl),
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot, history = reader.snapshot_and_history_of(reference)

    assert snapshot.evaluation_count == 500_000
    assert snapshot.planned_evaluations == 500_000
    assert snapshot.completed_generations == 25
    assert snapshot.history_is_sampled is True
    assert snapshot.result_sources == 25
    assert len(history) <= 4_200
    assert history[0].evaluation == 1
    assert history[-1].evaluation == 500_000
    assert calls == 25

    cached_snapshot, cached_history = reader.snapshot_and_history_of(
        reference
    )

    assert cached_snapshot == snapshot
    assert cached_history == history
    assert calls == 25


def test_generation_shards_produce_exact_diversity(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "diversity-run"
    generations = run_root / "generations"
    generations.mkdir(parents=True)

    records = (
        {
            "run_id": "diversity-run",
            "problem_id": "toy",
            "generation_id": 0,
            "candidate_index": 0,
            "candidate_id": "toy_g000000_c000000",
            "attempt_id": "toy_g000000_c000000_a000",
            "params": {"p0": 0.0, "p1": 0.0},
            "fitness": {"status": "ok", "objective": 4.0},
        },
        {
            "run_id": "diversity-run",
            "problem_id": "toy",
            "generation_id": 0,
            "candidate_index": 1,
            "candidate_id": "toy_g000000_c000001",
            "attempt_id": "toy_g000000_c000001_a000",
            "params": {"p0": 1.0, "p1": 1.0},
            "fitness": {"status": "ok", "objective": 2.0},
        },
    )
    shard = generations / "g000000.jsonl"
    shard.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    (run_root / "summary.json").write_text(
        json.dumps(
            {
                "problem_id": "toy",
                "run_id": "diversity-run",
                "max_evaluations": 2,
                "evaluations_done": 2,
                "completed_generations": 1,
                "finalized": True,
                "objective": {"direction": "minimize"},
            }
        ),
        encoding="utf-8",
    )

    reader = GowFilesystemRunReader(results_root)
    reference = reader.discover_runs()[0]
    snapshot, _history = reader.snapshot_and_history_of(reference)

    assert len(snapshot.population_diversity) == 1
    observation = snapshot.population_diversity[0]
    assert observation.generation_id == 0
    assert observation.population_size == 2
    assert observation.active_dimensions == 2
    assert observation.spread > 0.0


def test_overview_shows_completed_and_planned_evaluations(qtbot) -> None:
    from gow_monitor.domain import (
        ObjectiveDirection,
        RunReference,
        RunSnapshot,
        RunState,
    )

    page = OverviewPage()
    qtbot.addWidget(page)
    snapshot = RunSnapshot(
        reference=RunReference(
            run_id="large-run",
            run_root=Path("results/runs/large-run"),
            direction=ObjectiveDirection.MINIMIZE,
        ),
        state=RunState.RUNNING,
        evaluation_count=20_000,
        failed_evaluations=0,
        result_sources=1,
        successful_evaluations=20_000,
        planned_evaluations=500_000,
    )

    page.render_snapshot(snapshot, ())

    assert page.cards["evaluations"].value_label.text() == (
        "20,000 / 500,000"
    )
    assert "4.00% completed" in (
        page.cards["evaluations"].detail_label.text()
    )
