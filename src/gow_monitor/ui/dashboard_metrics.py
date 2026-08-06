from __future__ import annotations

import math
import statistics
from collections.abc import Iterable

from gow_monitor.domain import (
    EvaluationPoint,
    ObjectiveDirection,
    PopulationDiversityPoint,
)


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
    return sample_series(float(point.evaluation) for point in points)


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

def population_diversity_series(
    history: Iterable[EvaluationPoint],
) -> tuple[PopulationDiversityPoint, ...]:
    """Calculate population spread and 95% PCA ellipse area by generation.

    Candidate parameters are normalized using the global observed range of the
    connected run. Constant dimensions are excluded.

    ``spread`` is the sum of marginal sample standard deviations across active
    normalized dimensions. It measures total axis-aligned population width.

    ``ellipse_area`` is the area of the 95% confidence ellipse defined by the
    two dominant eigenvalues of the normalized sample covariance matrix. It
    measures the occupied area in the dominant two-dimensional PCA subspace.
    """

    points = tuple(
        point
        for point in history
        if point.generation_id is not None and point.parameters
    )
    if not points:
        return ()

    parameter_maps = tuple(point.parameter_map for point in points)
    common_names = set(parameter_maps[0])
    for parameter_map in parameter_maps[1:]:
        common_names.intersection_update(parameter_map)
    if not common_names:
        return ()

    ordered_names = tuple(sorted(common_names))
    minima = {
        name: min(parameter_map[name] for parameter_map in parameter_maps)
        for name in ordered_names
    }
    maxima = {
        name: max(parameter_map[name] for parameter_map in parameter_maps)
        for name in ordered_names
    }
    active_names = tuple(
        name
        for name in ordered_names
        if not math.isclose(
            minima[name],
            maxima[name],
            rel_tol=0.0,
            abs_tol=1e-15,
        )
    )

    grouped: dict[int, list[EvaluationPoint]] = {}
    for point in points:
        assert point.generation_id is not None
        grouped.setdefault(point.generation_id, []).append(point)

    observations: list[PopulationDiversityPoint] = []
    for generation_id in sorted(grouped):
        generation = grouped[generation_id]
        evaluation = max(point.evaluation for point in generation)
        vectors = tuple(
            tuple(
                (
                    point.parameter_map[name] - minima[name]
                ) / (
                    maxima[name] - minima[name]
                )
                for name in active_names
            )
            for point in generation
        )

        covariance = _sample_covariance(vectors)
        spread = sum(
            math.sqrt(max(0.0, covariance[index][index]))
            for index in range(len(covariance))
        )
        ellipse_area = _confidence_ellipse_area(covariance)

        observations.append(
            PopulationDiversityPoint(
                generation_id=generation_id,
                evaluation=evaluation,
                spread=spread,
                ellipse_area=ellipse_area,
                population_size=len(generation),
                active_dimensions=len(active_names),
            )
        )

    return tuple(observations)


def _sample_covariance(
    vectors: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    if len(vectors) < 2 or not vectors or not vectors[0]:
        return ()

    dimensions = len(vectors[0])
    means = tuple(
        statistics.fmean(vector[index] for vector in vectors)
        for index in range(dimensions)
    )
    denominator = len(vectors) - 1
    return tuple(
        tuple(
            sum(
                (vector[row] - means[row])
                * (vector[column] - means[column])
                for vector in vectors
            ) / denominator
            for column in range(dimensions)
        )
        for row in range(dimensions)
    )


def _confidence_ellipse_area(
    covariance: tuple[tuple[float, ...], ...],
) -> float:
    if len(covariance) < 2:
        return 0.0

    first_value, first_vector = _dominant_eigenpair(covariance)
    if first_value <= 0.0 or not first_vector:
        return 0.0

    second_value, _second_vector = _dominant_eigenpair(
        covariance,
        orthogonal_to=(first_vector,),
    )
    if second_value <= 0.0:
        return 0.0

    chi_square_95_df2 = 5.991464547107979
    return (
        math.pi
        * chi_square_95_df2
        * math.sqrt(first_value * second_value)
    )


def _dominant_eigenpair(
    matrix: tuple[tuple[float, ...], ...],
    *,
    orthogonal_to: tuple[tuple[float, ...], ...] = (),
) -> tuple[float, tuple[float, ...]]:
    size = len(matrix)
    if size == 0:
        return 0.0, ()

    seed_candidates = (
        tuple(1.0 / (index + 1.0) for index in range(size)),
        *tuple(
            tuple(1.0 if index == basis else 0.0 for index in range(size))
            for basis in range(size)
        ),
    )
    vector: tuple[float, ...] = ()
    for candidate in seed_candidates:
        vector = _normalize_vector(
            _project_orthogonal(candidate, orthogonal_to)
        )
        if vector:
            break
    if not vector:
        return 0.0, ()

    for _iteration in range(96):
        product = tuple(
            sum(matrix[row][column] * vector[column] for column in range(size))
            for row in range(size)
        )
        product = _project_orthogonal(product, orthogonal_to)
        next_vector = _normalize_vector(product)
        if not next_vector:
            return 0.0, vector

        same_direction = sum(
            (next_vector[index] - vector[index]) ** 2
            for index in range(size)
        )
        opposite_direction = sum(
            (next_vector[index] + vector[index]) ** 2
            for index in range(size)
        )
        vector = next_vector
        if min(same_direction, opposite_direction) <= 1e-24:
            break

    product = tuple(
        sum(matrix[row][column] * vector[column] for column in range(size))
        for row in range(size)
    )
    eigenvalue = sum(
        vector[index] * product[index]
        for index in range(size)
    )
    return max(0.0, eigenvalue), vector


def _project_orthogonal(
    values: tuple[float, ...],
    basis_vectors: tuple[tuple[float, ...], ...],
) -> tuple[float, ...]:
    projected = list(values)
    for basis in basis_vectors:
        coefficient = sum(
            projected[index] * basis[index]
            for index in range(len(projected))
        )
        for index in range(len(projected)):
            projected[index] -= coefficient * basis[index]
    return tuple(projected)


def _normalize_vector(values: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-15:
        return ()
    return tuple(value / norm for value in values)
