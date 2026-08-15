"""Tests for LTTB downsampling."""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.lttb import downsample_series, lttb_downsample


def test_lttb_returns_all_when_small() -> None:
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [1.0, 2.0, 3.0, 4.0]
    out = lttb_downsample(xs, ys, 1000)
    assert out == [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]


def test_lttb_preserves_endpoints() -> None:
    xs = [float(i) for i in range(100)]
    ys = [float(i * i) for i in range(100)]
    out = lttb_downsample(xs, ys, 10)
    assert out[0] == (0.0, 0.0)
    assert out[-1] == (99.0, 99.0 * 99.0)
    assert len(out) <= 10
    # x must remain monotonic
    xs_out = [p[0] for p in out]
    assert xs_out == sorted(xs_out)


def test_lttb_empty() -> None:
    assert lttb_downsample([], [], 1000) == []


def test_lttb_threshold_less_than_3() -> None:
    xs = [1.0, 2.0, 3.0]
    ys = [1.0, 5.0, 1.0]
    out = lttb_downsample(xs, ys, 2)
    assert out == [(1.0, 1.0), (2.0, 5.0), (3.0, 1.0)]


def test_downsample_series_datetime() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pairs = [(t0, 1.0), (t0.replace(minute=1), 2.0), (t0.replace(minute=2), 3.0)]
    out = downsample_series(pairs, threshold=1000)
    assert len(out) == 3
    assert out[0] == (0.0, 1.0)
    assert out[-1][1] == 3.0


def test_downsample_series_empty() -> None:
    assert downsample_series([], 1000) == []


def test_downsample_series_skips_none_values() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pairs = [
        (t0, None),
        (t0.replace(minute=1), 2.0),
        (t0.replace(minute=2), None),
        (t0.replace(minute=3), 8.0),
    ]
    out = downsample_series(pairs, threshold=1000)
    # None values must be dropped, never converted to NaN.
    assert all(p[1] == p[1] for p in out)  # no NaN
    assert len(out) == 2
    assert out[0] == (0.0, 2.0)
    assert out[-1] == (120.0, 8.0)


def test_downsample_series_all_none() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = downsample_series([(t0, None), (t0.replace(minute=1), None)], 1000)
    assert out == []