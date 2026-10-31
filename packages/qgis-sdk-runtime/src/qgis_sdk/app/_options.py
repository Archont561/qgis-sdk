"""The flags an app launcher accepts, parsed before any Qt import.

``qgis_sdk.app.main(app)`` is what ``python -m <plugin>``, the console script a
``qgis-sdk build --target app`` distribution installs and ``qgis-sdk run`` all
call, so the flags live in one place and are proven without a toolkit:

A launcher opens a window unless it is told not to. The flags are:

``--headless``
    no window and no ``ctx.ui``; jobs, the project and the services still work.
``--once``
    start, deliver what is already queued, stop - the smoke run a script or a CI
    job can make. It is also how ``qgis-sdk run --once`` proves a project starts.
``--grace SECONDS``
    how long shutdown waits for running jobs before naming and abandoning them
    (decision-69 point 2); ``15`` unless the launcher says otherwise.
``--title TITLE``
    the window title, when the application's own title is not what a launcher
    wants to show.
``--``
    everything after it belongs to the toolkit, not to the SDK (``-platform
    offscreen`` and friends). Unrecognised options are passed through too, so a
    launcher can hand Qt its own flags without this module knowing them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ._session import GRACE_SECONDS, QgisSdkAppError

__all__ = ["AppOptions", "parse_argv"]

#: The flag that ends the SDK's own options; the rest is the toolkit's.
SEPARATOR = "--"


@dataclass(frozen=True, slots=True)
class AppOptions:
    """What a launcher asked for, in the terms :func:`qgis_sdk.app.run` takes."""

    gui: bool = True
    once: bool = False
    grace: float = GRACE_SECONDS
    title: str | None = None
    argv: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, object]:
        return {
            "gui": self.gui,
            "once": self.once,
            "grace": self.grace,
            "title": self.title,
            "argv": list(self.argv),
        }


def parse_argv(argv: Sequence[str] | None = None) -> AppOptions:
    """Read the SDK's flags from ``argv`` (``sys.argv[1:]`` when ``None``).

    A value that cannot be read refuses by name instead of starting an app with a
    grace period the user did not ask for: a launcher's exit code is all a
    double-click gives back.
    """
    remaining = list(argv) if argv is not None else None
    if remaining is None:
        import sys

        remaining = list(sys.argv[1:])
    gui = True
    once = False
    grace = GRACE_SECONDS
    title: str | None = None
    toolkit: list[str] = []
    index = 0
    while index < len(remaining):
        argument = remaining[index]
        index += 1
        if argument == SEPARATOR:
            toolkit.extend(remaining[index:])
            break
        if argument == "--headless":
            gui = False
        elif argument in {"--gui", "--windowed"}:
            gui = True
        elif argument == "--once":
            once = True
        elif argument in {"--grace", "--title"}:
            if index >= len(remaining):
                raise QgisSdkAppError(f"{argument} needs a value")
            value = remaining[index]
            index += 1
            if argument == "--grace":
                grace = _seconds(value)
            else:
                title = value
        elif argument.startswith("--grace="):
            grace = _seconds(argument.partition("=")[2])
        elif argument.startswith("--title="):
            title = argument.partition("=")[2]
        else:
            toolkit.append(argument)
    return AppOptions(gui=gui, once=once, grace=grace, title=title, argv=tuple(toolkit))


def _seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise QgisSdkAppError(f"--grace wants seconds, got {value!r}") from None
    if seconds < 0:
        raise QgisSdkAppError(f"--grace must not be negative, got {value!r}")
    return seconds
