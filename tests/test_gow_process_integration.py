from __future__ import annotations

from pathlib import Path

import pytest

from gow_monitor.app import build_parser
from gow_monitor.domain import GowProcessResourceSnapshot
from gow_monitor.ui.main_window import MainWindow
from gow_monitor.ui.widgets import ResourcesPanel


def _gow_snapshot() -> GowProcessResourceSnapshot:
    return GowProcessResourceSnapshot(
        captured_at=10.0,
        root_pid=43210,
        root_name="gow.exe",
        available=True,
        status="GOW process tree telemetry available",
        cpu_process_percent=160.0,
        cpu_host_percent=20.0,
        memory_rss_bytes=512 * 1024**2,
        process_count=4,
        child_process_count=3,
        thread_count=12,
        logical_cores=8,
        active_pids=(43210, 43211, 43212, 43213),
    )


def test_cli_accepts_results_root_and_gow_pid() -> None:
    arguments = build_parser().parse_args(
        [
            "--results-root",
            "temporary-results",
            "--gow-pid",
            "43210",
        ]
    )

    assert arguments.results_root == Path("temporary-results")
    assert arguments.gow_pid == 43210


@pytest.mark.parametrize("invalid_pid", ["0", "-1", "not-a-pid"])
def test_cli_rejects_invalid_gow_pid(invalid_pid: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--gow-pid", invalid_pid])


def test_main_window_attaches_requested_gow_pid(qtbot) -> None:
    window = MainWindow(gow_pid=43210)
    qtbot.addWidget(window)

    assert window.resource_monitor.gow_pid == 43210

    window.resource_monitor.stop()


def test_resources_panel_renders_gow_process_tree(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    snapshot = _gow_snapshot()
    panel.render_gow_process(snapshot, (snapshot,))

    assert panel.tiles["gow_cpu"].gauge is not None
    assert panel.tiles["gow_cpu"].gauge.value == pytest.approx(20.0)
    assert panel.tiles["gow_memory"].value_label.text() == "512.0 MiB"
    assert panel.tiles["gow_processes"].value_label.text() == "4"
    assert panel.tiles["gow_threads"].value_label.text() == "12"
    assert "PID 43210" in panel.tiles["gow_processes"].detail_label.text()


def test_resources_panel_reports_missing_process_contract(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    snapshot = GowProcessResourceSnapshot.unavailable(
        captured_at=10.0,
        status="No GOW process is attached",
    )
    panel.render_gow_process(snapshot)

    assert panel.tiles["gow_cpu"].value_label.text() == "N/A"
    assert "No GOW process is attached" in (
        panel.tiles["gow_cpu"].detail_label.text()
    )
