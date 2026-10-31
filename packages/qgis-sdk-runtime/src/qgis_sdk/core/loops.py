"""Background loops a host starts, named so stopping it can say what it stopped.

decision-69 point 4: every loop the SDK starts on a host's behalf - the job pump,
a development reload watcher, an application host's own timer - carries a name,
and stopping a runtime enumerates what is still running instead of assuming it
stopped. A host records each loop here when it starts it and hands the registry
to :meth:`~qgis_sdk.core.ResourceScope`-owning shutdown, which stops them in the
reverse order they were added and reports the state each one reached.

Nothing here imports Qt: a loop is anything with a name, a ``running`` flag and a
``stop()`` - a ``QTimer``-driven pump, a polling watcher, a fake in a test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["LoopRegistry", "LoopState", "NamedLoop"]


@runtime_checkable
class NamedLoop(Protocol):
    """What a host registers: a name, whether it runs, and how it stops."""

    @property
    def name(self) -> str:
        """How the loop is named in a shutdown report and in the log."""

    @property
    def running(self) -> bool:
        """Whether the loop is armed right now, without stopping it."""

    def stop(self) -> None:
        """Disarm the loop; safe to call when it never started."""


@dataclass(frozen=True, slots=True)
class LoopState:
    """One loop's name and whether it is still armed."""

    name: str
    running: bool

    def __str__(self) -> str:
        return f"{self.name} ({'running' if self.running else 'stopped'})"


class LoopRegistry:
    """The loops one host started, in start order, with the names it gave them.

    Names are unique per registry: a host that starts two timers has to say what
    each is for, and a duplicate is a programming error rather than a silent
    overwrite - the report would otherwise name a loop that is no longer the one
    running under that name.
    """

    __slots__ = ("_loops",)

    def __init__(self, loops: Iterable[NamedLoop] = ()) -> None:
        self._loops: list[NamedLoop] = []
        for loop in loops:
            self.add(loop)

    def add(self, loop: NamedLoop) -> NamedLoop:
        """Record ``loop`` under its name; returns it for chaining."""
        name = loop.name
        if any(existing.name == name for existing in self._loops):
            raise ValueError(f"a loop named {name!r} is already registered")
        self._loops.append(loop)
        return loop

    def run(self, loop: NamedLoop) -> NamedLoop:
        """Start and record ``loop``: the one call a host makes."""
        start = getattr(loop, "start", None)
        if start is not None:
            start()
        return self.add(loop)

    def get(self, name: str) -> NamedLoop | None:
        """The loop registered as ``name``, or ``None``."""
        return next((loop for loop in self._loops if loop.name == name), None)

    def inventory(self) -> tuple[LoopState, ...]:
        """What is registered right now, in start order, without stopping it."""
        return tuple(LoopState(loop.name, bool(loop.running)) for loop in self._loops)

    def stop_all(self) -> tuple[LoopState, ...]:
        """Stop every loop, last started first, and report what each reached.

        The report is taken after each ``stop()``, so a loop that refuses to
        disarm shows up as still running instead of being assumed stopped. One
        failure does not strand the rest: the exception is re-raised only after
        every loop was asked, naming the loops that could not be stopped.
        """
        failures: list[tuple[str, BaseException]] = []
        for loop in reversed(self._loops):
            try:
                loop.stop()
            except BaseException as error:  # noqa: BLE001 - reported, not swallowed
                failures.append((loop.name, error))
        states = tuple(
            LoopState(loop.name, bool(loop.running)) for loop in reversed(self._loops)
        )
        if failures:
            names = ", ".join(f"{name} ({error})" for name, error in failures)
            raise RuntimeError(f"could not stop the background loops: {names}")
        return states

    def __len__(self) -> int:
        return len(self._loops)

    def __repr__(self) -> str:
        names = ", ".join(state.name for state in self.inventory())
        return f"LoopRegistry({names})"
