from __future__ import annotations

import math
import statistics
from collections.abc import Iterable

from gow_monitor.domain import EvaluationPoint, ObjectiveDirection


def sample_series(
    values: Iterable[float],
    *,
    max_points: int = 36,
) -> tuple[float, ...]:
    """Return an evenly sampled series suitable for compact sparklines."""

    series = tuple(float(value) for value in values if math.isfinite(float(value)))
    if max_points < 2:
        raise ValueError("max_points must be at least 2")
    if len(series) <= max_points:
        return series

    last_index = len(series) - 1
    indexes = {
        round(position * last_index / (max_points - 1))
        for position in range(max_points)
    }
    return tuple(series[index] for index in sorted(indexes))


def best_series(history: Iterable[EvaluationPoint]) -> tuple[float, ...]:
    return sample_series(
        point.best_so_far
        for point in history
        if point.best_so_far is not None
    )


def cumulative_evaluations_series(
    history: Iterable[EvaluationPoint],
) -> tuple[float, ...]:
    points = tuple(history)
    if not points:
        return ()
    return sample_series(float(index) for index in range(1, len(points) + 1))


def rolling_valid_rate_series(
    history: Iterable[EvaluationPoint],
    *,
    window_size: int = 50,
) -> tuple[float, ...]:
    return _rolling_rate_series(history, window_size=window_size, valid=True)


def rolling_failure_rate_series(
    history: Iterable[EvaluationPoint],
    *,
    window_size: int = 50,
) -> tuple[float, ...]:
    return _rolling_rate_series(history, window_size=window_size, valid=False)


def _rolling_rate_series(
    history: Iterable[EvaluationPoint],
    *,
    window_size: int,
    valid: bool,
) -> tuple[float, ...]:
    if window_size < 1:
        raise ValueError("window_size must be positive")

    points = tuple(history)
    rates: list[float] = []
    for end_index in range(1, len(points) + 1):
        start_index = max(0, end_index - window_size)
        window = points[start_index:end_index]
        if valid:
            matching = sum(point.is_valid for point in window)
        else:
            matching = sum(not point.is_valid for point in window)
        rates.append(matching / len(window) * 100.0)
    return sample_series(rates)


def recent_improvement_percent(
    history: Iterable[EvaluationPoint],
    direction: ObjectiveDirection,
    *,
    window_size: int = 100,
) -> float | None:
    """Measure incumbent improvement within the latest evaluation window."""

    if window_size < 2:
        raise ValueError("window_size must be at least 2")

    points = tuple(history)[-window_size:]
    best_values = tuple(
        point.best_so_far
        for point in points
        if point.best_so_far is not None
    )
    if len(best_values) < 2:
        return None

    start = best_values[0]
    end = best_values[-1]
    if start == 0.0:
        return 0.0 if end == 0.0 else None

    if direction is ObjectiveDirection.MAXIMIZE:
        change = end - start
    else:
        change = start - end
    return max(0.0, change / abs(start) * 100.0)


def recent_improvement_series(
    history: Iterable[EvaluationPoint],
    direction: ObjectiveDirection,
    *,
    window_size: int = 100,
) -> tuple[float, ...]:
    points = tuple(history)
    values: list[float] = []
    for end_index in range(1, len(points) + 1):
        start_index = max(0, end_index - window_size)
        value = recent_improvement_percent(
            points[start_index:end_index],
            direction,
            window_size=window_size,
        )
        values.append(value if value is not None else 0.0)
    return sample_series(values)


def objective_variability_percent(
    history: Iterable[EvaluationPoint],
    *,
    window_size: int = 100,
) -> float | None:
    """Return the population coefficient of variation as a percentage.

    The window is defined over evaluations first. Invalid evaluations are then
    removed, so failures inside the latest window reduce the number of
    objective values used by the calculation.
    """

    if window_size < 2:
        raise ValueError("window_size must be at least 2")

    objectives = [
        point.objective
        for point in tuple(history)[-window_size:]
        if point.is_valid and point.objective is not None
    ]
    if len(objectives) < 2:
        return None

    mean = statistics.fmean(objectives)
    deviation = statistics.pstdev(objectives)
    if mean == 0.0:
        return 0.0 if deviation == 0.0 else None
    return deviation / abs(mean) * 100.0


def objective_series(
    history: Iterable[EvaluationPoint],
    *,
    window_size: int = 100,
) -> tuple[float, ...]:
    values = [
        point.objective
        for point in tuple(history)[-window_size:]
        if point.is_valid and point.objective is not None
    ]
    return sample_series(values)
