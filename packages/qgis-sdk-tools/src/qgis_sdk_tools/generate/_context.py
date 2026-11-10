"""What rendering needs, gathered once so a renderer takes a single argument."""

from __future__ import annotations

from dataclasses import dataclass

from qgis_sdk_tools.generate._contract import _Surface
from qgis_sdk_tools.generate._names import _Action, _Stream
from qgis_sdk_tools.generate._naming import _Naming


@dataclass(frozen=True)
class _Rendering:
    """The surface, the declared operations, and the names they were given.

    Rendering is a function of these four things once collection is done, so
    handing them over as one object keeps a renderer's signature about what it
    needs instead of how the generator happened to assemble it.
    """

    surface: _Surface
    actions: tuple[_Action, ...]
    streams: tuple[_Stream, ...]
    names: _Naming
