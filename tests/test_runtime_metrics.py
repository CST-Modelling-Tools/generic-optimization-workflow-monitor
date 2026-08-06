from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gow_monitor.domain import (
    ObjectiveDirection,
    RunReference,
    RunSnapshot,
    RunState,
)
from gow_monitor.infrastructure import GowFilesystemRunReader
from gow_monitor.ui.formatting import format_binary_bytes, format_fixed
from gow_monitor.ui.pages import OverviewPage


def _utc_timestamp(hour: int, minute: int, second: int = 0) -> float:
    return datetime(
        2026,
        8,
        6,
        hour,
        minute,
        second,
        tzinfo=timezone.utc,
    ).timestamp()


def test_non_objective_formatters_use_two_decimals() -> None:
    assert format_fixed(12.346) == "12.35"
    assert format_fixed(12.346, suffix="%") == "12.35%"
    assert format_binary_bytes(512 * 1024**2) == "512.00 MiB"


def test_reader_extracts_run_start_and_finish_from_shards(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "results"
    run_root = results_root / "runs" / "timed-run"
    generations = run_root / "generations"
    generations.mkdir(parents=True)

    records = (
        {
            "run_id": "timed-run",
            "problem_id": "timed-problem",
            "generation_id": 0,
            "candidate_index": 0,
            "candidate_id": "timed_g000000_c000000",
            "attempt_id": "timed_g000000_c000000_a000",
            "started_at": "2026-08-06T10:00:00Z",
            "finished_at": "2026-08-06T10:00:30Z",
            "fitness": {"status": "ok", "objective": 2.0},
        },
        {
            "run_id": "timed-run",
            "problem_id": "timed-problem",
            "generation_id": 0,
            "candidate_index": 1,
            "candidate_id": "timed_g000000_c000001",
            "attempt_id": "timed_g000000_c000001_a000",
            "started_at": "2026-08-06T10:01:00+00:00",
            "finished_at": "2026-08-06T10:02:00+00:00",
            "fitness": {"status": "ok", "objective": 1.0},
        },
    )
    (generations / "g000000.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    (run_root / "summary.json").write_text(
        json.dumps(
            {
                "problem_id": "timed-problem",
                "run_id": "timed-run",
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
    snapshot = reader.snapshot_of(reference)

    assert snapshot.run_started_at == _utc_timestamp(10, 0)
    assert snapshot.run_finished_at == _utc_timestamp(10, 2)


def test_completed_run_shows_final_duration_and_average_rate(
    qtbot,
) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)
    snapshot = RunSnapshot(
        reference=RunReference(
            run_id="completed-run",
            run_root=Path("results/runs/completed-run"),
            direction=ObjectiveDirection.MINIMIZE,
        ),
        state=RunState.COMPLETED,
        evaluation_count=240,
        failed_evaluations=0,
        result_sources=1,
        successful_evaluations=240,
        best_objective=1.234567890123,
        run_started_at=1_000.0,
        run_finished_at=1_120.0,
    )

    page.render_snapshot(snapshot, ())

    assert page.cards["elapsed"].value_label.text() == "00:02:00"
    assert page.cards["throughput"].value_label.text() == (
        "120.00 eval/min"
    )
    assert page.cards["elapsed"].detail_label.text() == "Final duration"
    assert page.cards["throughput"].detail_label.text() == "Final average"
    assert page.cards["best"].value_label.text() == "1.23456789012"
    page.runtime_timer.stop()


def test_running_timer_uses_current_time(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "gow_monitor.ui.pages.overview_page.time.time",
        lambda: 1_060.0,
    )
    page = OverviewPage()
    qtbot.addWidget(page)
    snapshot = RunSnapshot(
        reference=RunReference(
            run_id="running-run",
            run_root=Path("results/runs/running-run"),
            direction=ObjectiveDirection.MINIMIZE,
        ),
        state=RunState.RUNNING,
        evaluation_count=120,
        failed_evaluations=0,
        result_sources=1,
        successful_evaluations=120,
        run_started_at=1_000.0,
    )

    page.render_snapshot(snapshot, ())

    assert page.cards["elapsed"].value_label.text() == "00:01:00"
    assert page.cards["throughput"].value_label.text() == (
        "120.00 eval/min"
    )
    assert page.cards["elapsed"].detail_label.text() == "Running"
    assert page.cards["throughput"].detail_label.text() == (
        "Average since run start"
    )
    page.runtime_timer.stop()
