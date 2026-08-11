from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class HorizontalZoom:
    # Normalized horizontal viewport shared by custom Qt charts.

    start: float = 0.0
    end: float = 1.0
    minimum_span: float = 0.025

    @property
    def span(self) -> float:
        return self.end - self.start

    @property
    def active(self) -> bool:
        return self.start > 0.0 or self.end < 1.0

    def reset(self) -> None:
        self.start = 0.0
        self.end = 1.0

    def zoom_at(
        self,
        anchor: float,
        scale: float,
    ) -> None:
        if not math.isfinite(anchor) or not math.isfinite(scale):
            return
        if scale <= 0.0:
            return

        anchor = min(1.0, max(0.0, anchor))
        old_span = self.span
        new_span = min(
            1.0,
            max(self.minimum_span, old_span * scale),
        )

        absolute_anchor = self.start + anchor * old_span
        new_start = absolute_anchor - anchor * new_span
        new_end = new_start + new_span

        if new_start < 0.0:
            new_end -= new_start
            new_start = 0.0
        if new_end > 1.0:
            new_start -= new_end - 1.0
            new_end = 1.0

        self.start = max(0.0, new_start)
        self.end = min(1.0, new_end)

        if self.span >= 0.999:
            self.reset()

    def pan_display_fraction(self, fraction: float) -> None:
        if not self.active or not math.isfinite(fraction):
            return

        shift = fraction * self.span
        new_start = self.start + shift
        new_end = self.end + shift

        if new_start < 0.0:
            new_end -= new_start
            new_start = 0.0
        if new_end > 1.0:
            new_start -= new_end - 1.0
            new_end = 1.0

        self.start = max(0.0, new_start)
        self.end = min(1.0, new_end)

    def slice_bounds(self, count: int) -> tuple[int, int]:
        if count <= 2 or not self.active:
            return 0, count

        last_index = count - 1
        first = int(math.floor(self.start * last_index))
        last = int(math.ceil(self.end * last_index)) + 1

        first = max(0, min(first, count - 2))
        last = max(first + 2, min(last, count))
        return first, last
