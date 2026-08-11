from __future__ import annotations

import pytest

from gow_monitor.ui.widgets.chart_navigation import HorizontalZoom


def test_horizontal_zoom_focuses_around_anchor() -> None:
    zoom = HorizontalZoom()

    zoom.zoom_at(0.5, 0.5)

    assert zoom.active
    assert zoom.start == pytest.approx(0.25)
    assert zoom.end == pytest.approx(0.75)
    assert zoom.span == pytest.approx(0.5)


def test_horizontal_zoom_can_pan_and_reset() -> None:
    zoom = HorizontalZoom()
    zoom.zoom_at(0.5, 0.5)

    zoom.pan_display_fraction(0.25)

    assert zoom.start == pytest.approx(0.375)
    assert zoom.end == pytest.approx(0.875)

    zoom.reset()

    assert not zoom.active
    assert zoom.start == 0.0
    assert zoom.end == 1.0


def test_horizontal_zoom_returns_bounded_slice() -> None:
    zoom = HorizontalZoom()
    zoom.zoom_at(0.5, 0.2)

    first, last = zoom.slice_bounds(100)

    assert 0 <= first < last <= 100
    assert last - first < 100
    assert last - first >= 2
