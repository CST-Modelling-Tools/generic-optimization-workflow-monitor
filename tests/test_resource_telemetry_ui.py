from __future__ import annotations

from pathlib import Path

import pytest

from gow_monitor.app import build_parser
from gow_monitor.domain import (
    RunReference,
    RunSnapshot,
    RunState,
    SystemResourceSnapshot,
)
from gow_monitor.ui.main_window import MainWindow
from gow_monitor.ui.widgets import ResourcesPanel


def _resource_snapshot() -> SystemResourceSnapshot:
    return SystemResourceSnapshot(
        captured_at=1.0,
        cpu_percent=55.12567,
        per_core_percent=(10.0, 20.0, 90.0, 100.0),
        physical_cores=2,
        logical_cores=4,
        active_logical_cores=4,
        active_core_threshold_percent=5.0,
        memory_percent=60.98765,
        memory_used_bytes=6 * 1024**3,
        memory_total_bytes=10 * 1024**3,
        gpus=(),
        gpu_status="GPU telemetry intentionally hidden",
    )


def _run_snapshot(tmp_path: Path) -> RunSnapshot:
    return RunSnapshot(
        reference=RunReference(
            run_id="run-resources",
            run_root=tmp_path / "results" / "runs" / "run-resources",
            problem_id="toy",
        ),
        state=RunState.RUNNING,
        evaluation_count=5,
        failed_evaluations=0,
        result_sources=5,
        successful_evaluations=5,
    )


def test_resources_panel_renders_requested_resource_cards(
    qtbot,
    tmp_path: Path,
) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    panel.render(_run_snapshot(tmp_path))
    snapshot = _resource_snapshot()
    panel.render_system(snapshot, (snapshot,))

    assert tuple(panel.tiles) == (
        "cpu",
        "memory",
        "cores",
        "gow_memory",
        "sources",
    )
    assert panel.tiles["cpu"].gauge is not None
    assert panel.tiles["cpu"].gauge.value == pytest.approx(55.12567)
    assert panel.tiles["cpu"].value_label.text() == "55.13%"
    assert panel.tiles["memory"].gauge is not None
    assert panel.tiles["memory"].gauge.value == pytest.approx(60.98765)
    assert panel.tiles["memory"].value_label.text() == "60.99%"
    assert panel.tiles["cores"].value_label.text() == "4 / 4"
    assert panel.tiles["sources"].value_label.text() == "5"


def test_sidebar_is_hidden_until_navigation_is_implemented(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.sidebar.isHidden()
    window.resource_monitor.stop()


def test_cli_accepts_results_root() -> None:
    arguments = build_parser().parse_args(
        ["--results-root", "temporary-results"]
    )

    assert arguments.results_root == Path("temporary-results")


def test_resources_panel_uses_responsive_columns(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    assert panel.column_count == 3
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(0, 1).widget() is panel.tiles["memory"]
    assert panel.grid.itemAtPosition(0, 2).widget() is panel.tiles["cores"]
    assert panel.grid.itemAtPosition(1, 0).widget() is panel.tiles["gow_memory"]
    assert panel.grid.itemAtPosition(1, 1).widget() is panel.tiles["sources"]

    assert panel._columns_for_width(500) == 2
    panel._reflow_tiles(2)

    assert panel.column_count == 2
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(0, 1).widget() is panel.tiles["memory"]
    assert panel.grid.itemAtPosition(1, 0).widget() is panel.tiles["cores"]
    assert panel.grid.itemAtPosition(1, 1).widget() is panel.tiles["gow_memory"]
    assert panel.grid.itemAtPosition(2, 0).widget() is panel.tiles["sources"]

    assert panel._columns_for_width(320) == 1
    panel._reflow_tiles(1)

    assert panel.column_count == 1
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(4, 0).widget() is panel.tiles["sources"]
