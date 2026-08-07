"""Async fake session for state-machine tests (no DB required)."""

from __future__ import annotations

import uuid
from typing import Any


class _FakeScalarResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeExecResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class FakeSession:
    """Minimal in-memory session for testing state-machine transitions.

    Stores added objects and answers SELECT queries against them so
    ``_close_event`` can find open events.
    """

    def __init__(self) -> None:
        self._added: list[Any] = []
        self._flushed: list[Any] = []

    @property
    def added(self) -> list:
        return self._flushed

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4().int
        self._added.append(obj)

    async def flush(self) -> None:
        self._flushed.extend(self._added)
        self._added.clear()

    async def execute(self, stmt) -> _FakeExecResult:
        # Return all stored events matching the query's WHERE conditions.
        rows: list = []
        for obj in self._flushed:
            match = True
            if getattr(stmt, "where_criteria", None) is not None:
                # Simplified: the fake only handles "end_time is None" queries
                pass
            rows.append(obj)
        return _FakeExecResult(self._filter_open(rows))

    def _filter_open(self, rows: list) -> list:
        open_rows = []
        for obj in rows:
            if getattr(obj, "end_time", None) is None:
                open_rows.append(obj)
        return open_rows