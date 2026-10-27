"""``ctx.log``: structured records at four levels (decision-63, first step).

``ctx.log.info("buffer finished", features=12)`` produces one
:class:`LogRecord` carrying the plugin id, the level, the message and the
keyword fields. Where it lands is the host's business - ``QgsMessageLog``
under the plugin's tag natively, a list under the fake - and a view may
``subscribe`` to see the records as they are written (``LogView`` does).
Crash capture, ``diagnose`` and the agent transport come later (decision-63);
this module is the minimum the components need.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol

LogLevel = Literal["debug", "info", "warning", "error"]

LOG_LEVELS: tuple[LogLevel, ...] = ("debug", "info", "warning", "error")

LogListener = Callable[["LogRecord"], None]

__all__ = [
    "LOG_LEVELS",
    "Log",
    "LogBase",
    "LogLevel",
    "LogListener",
    "LogRecord",
]


@dataclass(frozen=True, slots=True)
class LogRecord:
    """One written record, as a backend or a subscriber sees it."""

    level: LogLevel
    message: str
    plugin: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    time: float = 0.0
    correlation: str | None = None

    def format(self) -> str:
        """``message key=value ...`` - the one-line form for plain sinks."""
        if not self.fields:
            return self.message
        rendered = " ".join(f"{key}={value!r}" for key, value in self.fields.items())
        return f"{self.message} {rendered}"


class Log(Protocol):
    """Write structured records at one of four levels; watch them arrive."""

    def debug(self, message: str, **fields: Any) -> None: ...

    def info(self, message: str, **fields: Any) -> None: ...

    def warning(self, message: str, **fields: Any) -> None: ...

    def error(self, message: str, **fields: Any) -> None: ...

    def subscribe(self, listener: LogListener) -> Callable[[], None]: ...


class LogBase:
    """The shared half of every ``Log``: levels, fields, subscribers.

    A backend subclasses it and implements ``_deliver(record)`` once; the
    four level methods build the record, deliver it and then hand it to
    every subscriber in registration order. ``subscribe`` returns the
    function that removes the listener again.
    """

    def __init__(self, plugin: str) -> None:
        self._plugin = plugin
        self._listeners: list[LogListener] = []

    @property
    def plugin(self) -> str:
        """The id the records carry (``QgsMessageLog``'s tag natively)."""
        return self._plugin

    def debug(self, message: str, **fields: Any) -> None:
        self._write("debug", message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._write("info", message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._write("warning", message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._write("error", message, fields)

    def subscribe(self, listener: LogListener) -> Callable[[], None]:
        """See every record written from now on; returns the unsubscribe."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _write(self, level: LogLevel, message: str, fields: Mapping[str, Any]) -> None:
        record = LogRecord(
            level=level,
            message=message,
            plugin=self._plugin,
            fields=MappingProxyType(dict(fields)),
            time=time.time(),
        )
        self._deliver(record)
        for listener in tuple(self._listeners):
            listener(record)

    def _deliver(self, record: LogRecord) -> None:
        raise NotImplementedError
