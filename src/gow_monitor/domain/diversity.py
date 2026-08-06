from __future__ import annotations

import math


def confidence_ellipse_area(
    covariance: tuple[tuple[float, ...], ...],
) -> float:
    """Return the 95% ellipse area of the two dominant covariance modes."""

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
            tuple(
                1.0 if index == basis else 0.0
                for index in range(size)
            )
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
            sum(
                matrix[row][column] * vector[column]
                for column in range(size)
            )
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
        sum(
            matrix[row][column] * vector[column]
            for column in range(size)
        )
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


def _normalize_vector(
    values: tuple[float, ...],
) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-15:
        return ()
    return tuple(value / norm for value in values)
