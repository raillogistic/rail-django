"""Lightweight timing context manager."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def profile_block(recorder, metric_name: str):
    start = perf_counter()
    try:
        yield
    finally:
        recorder(metric_name, perf_counter() - start)
