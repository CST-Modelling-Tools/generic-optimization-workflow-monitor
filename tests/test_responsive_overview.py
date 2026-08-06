from __future__ import annotations

from PySide6.QtCore import Qt

from gow_monitor.ui.main_window import MainWindow
from gow_monitor.ui.pages import OverviewPage
from gow_monitor.ui.widgets import ResourcesPanel


def test_metric_panel_height_tracks_row_count(qtbot) -> None:
    panel = ResourcesPanel()
    qtbot.addWidget(panel)

    panel._reflow_tiles(3)
    three_column_height = panel.minimumHeight()

    panel._reflow_tiles(2)
    two_column_height = panel.minimumHeight()

    panel._reflow_tiles(1)
    one_column_height = panel.minimumHeight()

    assert three_column_height >= 180
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


def test_main_window_wraps_overview_in_scroll_area(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.overview_scroll.widget() is window.overview_page
    assert window.overview_scroll.widgetResizable()

    window.resource_monitor.stop()


def test_overview_contains_diversity_chart_below_objective_chart(qtbot) -> None:
    page = OverviewPage()
    qtbot.addWidget(page)

    layout = page.progress_chart.parentWidget().layout()
    objective_index = layout.indexOf(page.progress_chart)
    diversity_index = layout.indexOf(page.diversity_chart)

    assert objective_index >= 0
    assert diversity_index > objective_index


def test_main_window_fits_overview_without_internal_scroll(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    qtbot.wait(50)

    assert window.overview_scroll.widget() is window.overview_page
    assert window.overview_scroll.widgetResizable()
    assert (
        window.overview_scroll.verticalScrollBarPolicy()
        is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert window.overview_page.minimumSizeHint().height() <= (
        window.overview_scroll.viewport().height()
    )

    window.resource_monitor.stop()
