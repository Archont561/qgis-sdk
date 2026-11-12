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


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_parse_argv_p1(_s):
    _s.gui = False


def _cc_parse_argv_p2(_s):
    _s.gui = True


def _cc_parse_argv_p3(_s):
    _s.once = True


def _cc_parse_argv_p4(_s):
    if _s.index >= len(_s.remaining):
        raise QgisSdkAppError(f"{_s.argument} needs a value")
    _s.value = _s.remaining[_s.index]
    _s.index += 1
    if _s.argument == "--grace":
        _s.grace = _seconds(_s.value)
    else:
        _s.title = _s.value


def _cc_parse_argv_p5(_s):
    _s.grace = _seconds(_s.argument.partition("=")[2])


def _cc_parse_argv_p6(_s):
    _s.title = _s.argument.partition("=")[2]


def _cc_parse_argv_p7(_s):
    _s.toolkit.append(_s.argument)


def _cc_parse_argv_p8(_s):
    _s.argument = _s.remaining[_s.index]
    _s.index += 1
    if _s.argument == SEPARATOR:
        _s.toolkit.extend(_s.remaining[_s.index :])
        return _CcBreak()


_CC_PARSE_ARGV_HANDLERS = (
    (lambda argument: argument == "--headless", _cc_parse_argv_p1),
    (lambda argument: argument in {"--gui", "--windowed"}, _cc_parse_argv_p2),
    (lambda argument: argument == "--once", _cc_parse_argv_p3),
    (lambda argument: argument in {"--grace", "--title"}, _cc_parse_argv_p4),
    (lambda argument: argument.startswith("--grace="), _cc_parse_argv_p5),
    (lambda argument: argument.startswith("--title="), _cc_parse_argv_p6),
    (lambda argument: True, _cc_parse_argv_p7),
)


def _cc_parse_argv_p9(_s):
    """Run the one phase that owns this option spelling."""
    for matches, phase in _CC_PARSE_ARGV_HANDLERS:
        if matches(_s.argument):
            return phase(_s)
    return None


def _cc_parse_argv_p10(_s):
    _s.remaining = list(_s.argv) if _s.argv is not None else None
    if _s.remaining is None:
        import sys

        _s.sys = sys

        _s.remaining = list(_s.sys.argv[1:])
    _s.gui = True
    _s.once = False
    _s.grace = GRACE_SECONDS
    _s.title: str | None = None
    _s.toolkit: list[str] = []
    _s.index = 0


def _cc_parse_argv_p11(_s):
    while _s.index < len(_s.remaining):
        _a = None
        for _p in (_cc_parse_argv_p8, _cc_parse_argv_p9):
            _r = _p(_s)
            if isinstance(_r, _CcReturn):
                return _r
            if isinstance(_r, (_CcBreak, _CcContinue)):
                _a = _r
                break
        if isinstance(_a, _CcBreak):
            break
        if isinstance(_a, _CcContinue):
            continue


def _cc_parse_argv_p12(_s):
    return _CcReturn(
        AppOptions(
            gui=_s.gui,
            once=_s.once,
            grace=_s.grace,
            title=_s.title,
            argv=tuple(_s.toolkit),
        )
    )


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
    _s = _CcState(**locals())
    for _p in (_cc_parse_argv_p10, _cc_parse_argv_p11, _cc_parse_argv_p12):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def _seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise QgisSdkAppError(f"--grace wants seconds, got {value!r}") from None
    if seconds < 0:
        raise QgisSdkAppError(f"--grace must not be negative, got {value!r}")
    return seconds
