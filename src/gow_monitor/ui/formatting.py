from __future__ import annotations

import math


def format_fixed(
    value: float | int | None,
    *,
    decimals: int = 4,
    suffix: str = "",
) -> str:
    """Format non-objective decimal values without scientific notation."""

    if decimals < 0:
        raise ValueError("decimals cannot be negative")
    if value is None or isinstance(value, bool):
        return "N/A"

    numeric = float(value)
    if not math.isfinite(numeric):
        return "N/A"
    return f"{numeric:.{decimals}f}{suffix}"


def format_binary_bytes(
    value: int | None,
    *,
    decimals: int = 4,
) -> str:
    """Format a byte count using binary units and fixed decimal precision."""

    if value is None:
        return "N/A"
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            return f"{size:.{decimals}f} {unit}"
        size /= 1024.0
    return f"{size:.{decimals}f} TiB"
