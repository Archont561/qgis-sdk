"""The listener's knobs: the rule each one has to satisfy, and the limits they mean."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ._errors import QgisSdkHttpError

MAX_BODY_BYTES = 1024 * 1024
"""One request body bound for every REST entry point."""

MAX_SESSIONS = 64
"""One session budget for every REST entry point."""

DEFAULT_CLOSE_GRACE = 2.0
"""How long a close waits for replies already owed to callers it just withdrew."""

DEFAULT_MAX_CONNECTIONS = 128
"""How many HTTP handlers may run at once unless the host says otherwise."""


@dataclass(frozen=True)
class _Capacity:
    """How many connections may run at once, and how many of them may be streams."""

    max_connections: int
    max_event_streams: int


@dataclass(frozen=True)
class _Timing:
    """The three durations a listener runs on."""

    request_read_timeout: float
    stream_write_timeout: float
    close_grace: float


def capacity(max_connections: Any, max_event_streams: Any) -> _Capacity:
    """Read the two connection budgets, refusing a cap that starves calls.

    The event-stream cap defaults to one sixteenth of the connections, so a
    host that names only what it cares about still leaves room for calls.
    """
    connections = _positive_count(max_connections, "max_connections")
    if max_event_streams is None:
        max_event_streams = min(16, connections - 1)
    if not _is_event_stream_cap(max_event_streams, connections):
        raise QgisSdkHttpError(
            "max_event_streams must leave at least one connection for calls"
        )
    return _Capacity(connections, int(max_event_streams))


def timing(
    request_read_timeout: Any, stream_write_timeout: Any, close_grace: Any
) -> _Timing:
    """Read the three durations, each under the rule its job implies."""
    read = _positive_duration(request_read_timeout, "request_read_timeout")
    write = _positive_duration(stream_write_timeout, "stream_write_timeout")
    grace = _non_negative_duration(close_grace, "close_grace")
    return _Timing(read, write, grace)


def positive(name: str, value: Any) -> float:
    """Read one option that must be a positive, finite number."""
    if not _is_positive_number(value):
        raise QgisSdkHttpError(f"{name} must be a positive finite number")
    return float(value)


def _positive_duration(value: Any, name: str) -> float:
    """Read one duration that must be greater than zero."""
    if not _is_positive_number(value):
        raise QgisSdkHttpError(f"{name} must be positive and finite")
    return float(value)


def _non_negative_duration(value: Any, name: str) -> float:
    """Read one duration that may be zero but not negative."""
    if not _is_non_negative_number(value):
        raise QgisSdkHttpError(f"{name} must be a non-negative finite number")
    return float(value)


def _positive_count(value: Any, name: str) -> int:
    """Read one count that must be a whole number of at least one."""
    if not _is_positive_count(value):
        raise QgisSdkHttpError(f"{name} must be a positive integer")
    return int(value)


def _is_number(value: object) -> bool:
    """Whether ``value`` is a real, finite number.

    ``bool`` is an ``int`` to Python and is not a duration to anybody, and an
    infinity or a NaN passes every comparison without meaning anything.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_positive_number(value: object) -> bool:
    """Whether ``value`` is a number greater than zero."""
    return _is_number(value) and value > 0


def _is_non_negative_number(value: object) -> bool:
    """Whether ``value`` is a number at least zero."""
    return _is_number(value) and value >= 0


def _is_positive_count(value: object) -> bool:
    """Whether ``value`` is a whole number of at least one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= 1


def _is_event_stream_cap(value: object, connections: int) -> bool:
    """Whether ``value`` caps streams and still leaves a connection for calls."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return 0 <= value < connections
