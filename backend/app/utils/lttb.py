"""Largest-Triangle-Three-Buckets (LTTB) downsampling.

Given a time-series of (timestamp, value) pairs, downsample to at most
``threshold`` points while preserving visual shape.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def lttb_downsample(
    xs: Sequence[float],
    ys: Sequence[float],
    threshold: int,
) -> list[tuple[float, float]]:
    """Downsample series to <= threshold points using LTTB.

    Implements the canonical Largest-Triangle-Three-Buckets algorithm
    (Steinarsson, 2013). Always preserves the first and last points.

    Args:
        xs: Timestamps (epoch seconds, monotonic increasing).
        ys: Values aligned with ``xs``.
        threshold: Maximum number of output points (>= 2).

    Returns:
        List of (x, y) tuples.
    """
    n = len(xs)
    if n == 0:
        return []
    if n <= threshold or threshold < 3:
        return list(zip(xs, ys))

    data_x = [float(v) for v in xs]
    data_y = [float(v) for v in ys]

    # Number of interior points to sample
    every = (n - 2) / (threshold - 2)
    sampled: list[tuple[float, float]] = [(data_x[0], data_y[0])]

    a = 0  # index of the last selected point
    for i in range(threshold - 2):
        # --- Average point of current bucket (exclusive end) ---
        avg_range_start = int(1 + i * every)
        avg_range_end = min(int(2 + (i + 1) * every), n - 1)
        if avg_range_start >= avg_range_end:
            avg_range_start = avg_range_end - 1

        avg_x = 0.0
        avg_y = 0.0
        count = avg_range_end - avg_range_start
        if count > 0:
            for j in range(avg_range_start, avg_range_end):
                avg_x += data_x[j]
                avg_y += data_y[j]
            avg_x /= count
            avg_y /= count
        else:
            avg_x = data_x[avg_range_start]
            avg_y = data_y[avg_range_start]

        # --- Range of candidate points to choose from ---
        range_off = int(i * every) + 1
        range_on = max(int((i + 1) * every) + 1, range_off + 1)
        range_on = min(range_on, n - 1)

        max_area = -1.0
        selected = range_off
        for j in range(range_off, range_on):
            # Triangle area between: last selected (a), avg point, candidate (j)
            area = abs(
                (data_x[a] - avg_x) * (data_y[j] - data_y[a])
                - (data_x[a] - data_x[j]) * (avg_y - data_y[a])
            )
            if area > max_area:
                max_area = area
                selected = j

        sampled.append((data_x[selected], data_y[selected]))
        a = selected

    sampled.append((data_x[n - 1], data_y[n - 1]))
    return sampled


def downsample_series(
    time_values: Iterable,
    threshold: int = 1000,
) -> list[tuple[float, float]]:
    """Convenience wrapper for (datetime, value) pairs -> LTTB output.

    Output x-axis uses epoch seconds relative to the first sample.
    """
    pairs = list(time_values)
    if not pairs:
        return []

    t0 = pairs[0][0].timestamp()
    xs = [p[0].timestamp() - t0 for p in pairs]
    ys = [float(p[1]) if p[1] is not None else float("nan") for p in pairs]
    return lttb_downsample(xs, ys, threshold)