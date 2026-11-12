"""Destination naming: keep provider-supplied names within the run directory."""

from __future__ import annotations

import re
from pathlib import Path

from qgis_sdk.models import ParameterInfo

from ._kinds import DEFAULT_EXTENSIONS

__all__ = ["destination_name", "destination_path"]

#: Every character a provider may name a parameter with that no file name may
#: carry. A model names the destinations Processing derives for its children
#: after the child and its output - ``native:centroids_1:CENTROIDS`` - so the
#: colon and the upper case are the normal case, not the hostile one.
_UNSAFE_IN_NAME = re.compile(r"[^a-z0-9_]+")

#: Device names a file may not be called on Windows, whatever the extension.
_RESERVED_NAMES: frozenset[str] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def destination_name(parameter: ParameterInfo) -> str:
    """Keep provider-supplied names and extensions within the run directory.

    The provider's name is *translated*, not refused: a registered algorithm
    names a destination ``OUTPUT`` and a model names it after the child that
    writes it (``native:centroids_1:CENTROIDS``), and neither is a file name
    this SDK writes untouched. Every run of characters outside
    ``[a-z0-9_]`` becomes one ``_``, which leaves no separator, no leading
    dot and no name that escapes the run directory. What is still refused is
    what translation cannot make safe: a name that translates to nothing, a
    Windows device name, and an extension outside ``[A-Za-z0-9]``.

    Two provider names can translate alike; ``plan_destinations`` refuses that
    collision rather than letting one output overwrite another. A name that
    carries a path separator is not translated but refused: no provider
    composes one, so it is a caller reaching out of the run directory, and
    answering it with a benign name would hide that.
    """
    if "/" in parameter.name or "\\" in parameter.name:
        raise ValueError(
            "an allocated destination has an unsafe provider-defined name or extension"
        )
    name = _UNSAFE_IN_NAME.sub("_", parameter.name.lower()).strip("_")[:128]
    return _destination_name_tail(name, parameter)


def _destination_name_tail(name: str, parameter: ParameterInfo) -> str:
    """Attach the extension a destination kind answers under."""
    extension = parameter.extension or DEFAULT_EXTENSIONS.get(parameter.kind, "out")
    if (
        not name
        or name in _RESERVED_NAMES
        or (
            parameter.kind != "folderDestination"
            and not re.fullmatch(r"[a-zA-Z0-9]{1,16}", extension)
        )
    ):
        raise ValueError(
            "an allocated destination has an unsafe provider-defined name or extension"
        )
    if parameter.kind == "folderDestination":
        return name
    return f"{name}.{extension}"


def destination_path(run_directory: Path, parameter: ParameterInfo) -> Path:
    """Place a qualified allocated destination directly in the run directory."""
    return run_directory / destination_name(parameter)
