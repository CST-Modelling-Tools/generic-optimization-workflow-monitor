from __future__ import annotations

from pathlib import Path

import pytest

from gow_monitor.app import build_parser
from gow_monitor.domain import (
    GpuResourceSnapshot,
    RunReference,
    RunSnapshot,
    RunState,
    SystemResourceSnapshot,
)
from gow_monitor.ui.main_window import MainWindow
from gow_monitor.ui.widgets import ResourcesPanel


def _resource_snapshot(*, gpu: bool = True) -> SystemResourceSnapshot:
    gpus = ()
    if gpu:
        gpus = (
            GpuResourceSnapshot(
                name="Test GPU",
                utilization_percent=45.0,
                memory_used_bytes=2 * 1024**3,
                memory_total_bytes=8 * 1024**3,
                backend="test",
            ),
        )

    return SystemResourceSnapshot(
        captured_at=1.0,
        cpu_percent=55.0,
        per_core_percent=(10.0, 20.0, 90.0, 100.0),
        physical_cores=2,
        logical_cores=4,
        active_logical_cores=4,
        active_core_threshold_percent=5.0,
        memory_percent=60.0,
        memory_used_bytes=6 * 1024**3,
        memory_total_bytes=10 * 1024**3,
        gpus=gpus,
        gpu_status="No supported GPU telemetry backend detected",
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


def test_resources_panel_renders_cpu_ram_cores_and_gpu(
    qtbot,
    tmp_path: Path,
) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    panel.render(_run_snapshot(tmp_path))
    snapshot = _resource_snapshot()
    panel.render_system(snapshot, (snapshot,))

    assert panel.tiles["cpu"].gauge is not None
    assert panel.tiles["cpu"].gauge.value == pytest.approx(55.0)
    assert panel.tiles["memory"].gauge is not None
    assert panel.tiles["memory"].gauge.value == pytest.approx(60.0)
    assert panel.tiles["cores"].value_label.text() == "4 / 4"
    assert panel.tiles["gpu"].gauge is not None
    assert panel.tiles["gpu"].gauge.value == pytest.approx(45.0)
    assert panel.tiles["sources"].value_label.text() == "5"


def test_resources_panel_displays_na_without_gpu(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    panel.render_system(_resource_snapshot(gpu=False))

    assert panel.tiles["gpu"].value_label.text() == "N/A"
    assert "No supported GPU telemetry backend" in (
        panel.tiles["gpu"].detail_label.text()
    )


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
    assert panel.grid.itemAtPosition(2, 2).widget() is panel.tiles["sources"]

    assert panel._columns_for_width(500) == 2
    panel._reflow_tiles(2)

    assert panel.column_count == 2
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(0, 1).widget() is panel.tiles["memory"]
    assert panel.grid.itemAtPosition(4, 0).widget() is panel.tiles["sources"]

    assert panel._columns_for_width(320) == 1
    panel._reflow_tiles(1)

    assert panel.column_count == 1
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(8, 0).widget() is panel.tiles["sources"]

    assert panel._columns_for_width(900) == 3
    panel._reflow_tiles(3)

    assert panel.column_count == 3
    assert panel.grid.itemAtPosition(0, 0).widget() is panel.tiles["cpu"]
    assert panel.grid.itemAtPosition(0, 1).widget() is panel.tiles["memory"]
    assert panel.grid.itemAtPosition(0, 2).widget() is panel.tiles["cores"]
    assert panel.grid.itemAtPosition(2, 2).widget() is panel.tiles["sources"]



def test_resources_panel_does_not_invent_gpu_utilization(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    gpu = GpuResourceSnapshot(
        name="Intel Iris Xe Graphics",
        backend="windows-cim",
        vendor="Intel",
        device_id="luid_0x00000000_0x00010850_phys_0",
        dedicated_memory_used_bytes=0,
        shared_memory_used_bytes=1024**3,
        committed_memory_bytes=1536 * 1024**2,
    )

    snapshot = SystemResourceSnapshot(
        captured_at=1.0,
        cpu_percent=10.0,
        per_core_percent=(10.0,),
        physical_cores=1,
        logical_cores=1,
        active_logical_cores=1,
        active_core_threshold_percent=5.0,
        memory_percent=20.0,
        memory_used_bytes=2 * 1024**3,
        memory_total_bytes=10 * 1024**3,
        gpus=(gpu,),
        gpu_status="Partial Windows GPU telemetry",
    )

    panel.render_system(snapshot, (snapshot,))

    assert panel.tiles["gpu"].value_label.text() == "N/A"
    assert panel.tiles["gpu"].gauge is not None
    assert panel.tiles["gpu"].gauge.value is None
    assert "Intel Iris Xe Graphics" in (
        panel.tiles["gpu"].detail_label.text()
    )
    assert "shared 1.0 GiB" in (
        panel.tiles["gpu"].detail_label.text()
    )
    assert "committed 1.5 GiB" in (
        panel.tiles["gpu"].detail_label.text()
    )
