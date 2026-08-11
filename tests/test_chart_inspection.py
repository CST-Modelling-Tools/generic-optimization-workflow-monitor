from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from gow_monitor.domain import (
    EvaluationPoint,
    ObjectiveDirection,
    PopulationDiversityPoint,
)
from gow_monitor.ui.widgets.objective_progress_chart import (
    ObjectiveProgressChart,
)
from gow_monitor.ui.widgets.population_diversity_chart import (
    PopulationDiversityChart,
)


def test_objective_chart_selects_nearest_series_point(qtbot) -> None:
    chart = ObjectiveProgressChart()
    qtbot.addWidget(chart)
    chart.resize(1000, 600)
    chart.set_interactive_navigation(True)

    history = tuple(
        EvaluationPoint(
            evaluation=index,
            candidate_id=f"candidate-{index}",
            status="ok",
            objective=1.0 / index,
            best_so_far=1.0 / index,
            mean_so_far=2.5 / index,
            median_so_far=1.7 / index,
            generation_id=(index - 1) // 10,
        )
        for index in range(1, 101)
    )
    chart.set_history(history, ObjectiveDirection.MINIMIZE)

    points = chart.visible_points()
    values = chart._numeric_values(points)
    scale = chart._select_scale(values)
    transformed = [
        chart._transform_value(value, scale)
        for value in values
    ]
    y_min, y_max = chart._expanded_bounds(
        transformed,
        clamp_zero=scale == "linear",
    )
    chart_rect = QRectF(
        62.0,
        30.0,
        max(10.0, chart.width() - 82.0),
        max(10.0, chart.height() - 68.0),
    )

    target = points[49]
    x = chart._map_x(
        target.evaluation,
        chart_rect,
        x_min=points[0].evaluation,
        x_max=points[-1].evaluation,
    )
    y = chart._map_y(
        target.best_so_far,
        chart_rect,
        y_min=y_min,
        y_max=y_max,
        scale=scale,
    )

    assert chart.inspect_at(QPointF(x, y))
    assert chart.selected_inspection == (
        "Best-so-far",
        target.evaluation,
    )


def test_diversity_chart_selects_spread_point(qtbot) -> None:
    chart = PopulationDiversityChart()
    qtbot.addWidget(chart)
    chart.resize(1000, 600)
    chart.set_interactive_navigation(True)

    samples = tuple(
        PopulationDiversityPoint(
            generation_id=index,
            evaluation=(index + 1) * 10,
            spread=0.2 + index * 0.05,
            ellipse_area=1.5 + index * 0.1,
            population_size=100,
            active_dimensions=2,
        )
        for index in range(20)
    )
    chart.set_precomputed_series(samples)

    visible = chart.visible_samples()
    first_generation = visible[0].generation_id
    last_generation = visible[-1].generation_id
    maximum = max(
        max(sample.spread, sample.ellipse_area)
        for sample in visible
    )
    y_max = max(0.1000, maximum * 1.1200)

    chart_rect = QRectF(
        54.0,
        28.0,
        max(10.0, chart.width() - 70.0),
        max(10.0, chart.height() - 60.0),
    )
    spread_points = chart._map_series(
        visible,
        "spread",
        chart_rect,
        first_generation=first_generation,
        last_generation=last_generation,
        y_max=y_max,
    )

    target = visible[8]

    assert chart.inspect_at(spread_points[8])
    assert chart.selected_inspection == (
        "Spread",
        target.generation_id,
        target.evaluation,
    )
