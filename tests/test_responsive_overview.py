from __future__ import annotations

from gow_monitor.domain import (
    GpuResourceSnapshot,
    SystemResourceSnapshot,
)
from gow_monitor.ui.main_window import MainWindow
from gow_monitor.ui.pages import OverviewPage
from gow_monitor.ui.widgets import ResourcesPanel


def _system_snapshot() -> SystemResourceSnapshot:
    gpu = GpuResourceSnapshot(
        name="Intel(R) Iris(R) Xe Graphics",
        utilization_percent=0.0,
        backend="windows-cim",
        device_id="luid_0x00000000_0x00010850_phys_0",
        vendor="Intel",
        dedicated_memory_used_bytes=0,
        shared_memory_used_bytes=1024**3,
        committed_memory_bytes=1536 * 1024**2,
    )

    return SystemResourceSnapshot(
        captured_at=1.0,
        cpu_percent=25.0,
        per_core_percent=(
            10.0,
            20.0,
            30.0,
            40.0,
        ),
        physical_cores=2,
        logical_cores=4,
        active_logical_cores=4,
        active_core_threshold_percent=5.0,
        memory_percent=40.0,
        memory_used_bytes=4 * 1024**3,
        memory_total_bytes=10 * 1024**3,
        gpus=(gpu,),
        gpu_status="GPU telemetry available",
    )


def test_metric_panel_height_tracks_row_count(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    panel._reflow_tiles(3)
    three_column_height = panel.minimumHeight()

    panel._reflow_tiles(2)
    two_column_height = panel.minimumHeight()

    panel._reflow_tiles(1)
    one_column_height = panel.minimumHeight()

    assert three_column_height >= 350
    assert two_column_height > three_column_height
    assert one_column_height > two_column_height


def test_overview_lower_panels_can_stack(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)

    page._reflow_lower_panels(stacked=True)

    assert page.lower_panels_stacked is True
    assert (
        page.lower_layout.itemAtPosition(0, 0).widget()
        is page.search_behavior_panel
    )
    assert (
        page.lower_layout.itemAtPosition(1, 0).widget()
        is page.resources_panel
    )

    page._reflow_lower_panels(stacked=False)

    assert page.lower_panels_stacked is False
    assert (
        page.lower_layout.itemAtPosition(0, 0).widget()
        is page.search_behavior_panel
    )
    assert (
        page.lower_layout.itemAtPosition(0, 1).widget()
        is page.resources_panel
    )


def test_main_window_wraps_overview_in_scroll_area(
    qtbot,
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert (
        window.overview_scroll.widget()
        is window.overview_page
    )
    assert window.overview_scroll.widgetResizable()

    window.resource_monitor.stop()


def test_gpu_card_uses_short_visible_detail(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    snapshot = _system_snapshot()
    panel.render_system(snapshot, (snapshot,))

    detail = panel.tiles["gpu"].detail_label.text()
    tooltip = panel.tiles["gpu"].toolTip()

    assert detail.count("\n") == 1
    assert "Intel Iris Xe Graphics" in detail
    assert "shared 1.0 GiB" in detail
    assert "committed 1.5 GiB" in detail

    assert "windows-cim" in tooltip
    assert (
        "luid_0x00000000_0x00010850_phys_0"
        in tooltip
    )
    assert "Shared memory used: 1.0 GiB" in tooltip
