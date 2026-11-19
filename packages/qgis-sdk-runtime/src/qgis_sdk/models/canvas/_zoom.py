"""What ``zoom_to`` is aimed at, and the checks that keep a target honest.

One model rather than three methods, because the three kinds share an answer (the
extent the canvas landed on) and a caller picks one with a constructor rather
than by naming a kind string.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ._checks import is_number
from ._extent import CanvasExtent

__all__ = ["MAX_ZOOM_MARGIN", "ZOOM_KINDS", "ZoomKind", "ZoomTarget"]

#: What ``zoom_to`` may be aimed at. ``layer`` and ``selection`` name a layer;
#: ``extent`` carries the box, so a page can zoom to what it computed.
ZOOM_KINDS = ("layer", "selection", "extent")

#: The largest margin ``zoom_to`` accepts, as a fraction. Ten times the target
#: is already a map nobody asked for; a larger number is a unit mistake, and it
#: is refused by name rather than drawn.
MAX_ZOOM_MARGIN = 10.0

ZoomKind = Literal["layer", "selection", "extent"]


@dataclass(frozen=True, slots=True)
class ZoomTarget:
    """What ``zoom_to`` is aimed at: a layer, its selection, or a box.

    One model rather than three methods, because the three share an answer (the
    extent the canvas landed on) and a caller picks one with :meth:`layer`,
    :meth:`selection` or :meth:`to_extent` rather than by naming a kind string.

    Attributes:
        kind: What is aimed at: ``layer``, ``selection`` or ``extent``.
        layer_id: The layer to frame, for the two layer kinds.
        extent: The box to frame, for the ``extent`` kind.
        margin: How much of the target's span to leave around it, as a fraction.
    """

    kind: ZoomKind
    layer_id: str | None = None
    extent: CanvasExtent | None = None
    #: How much of the target's surroundings to include, as a fraction of its
    #: size: ``0.1`` leaves a tenth of the target's span on every side.
    margin: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ZOOM_KINDS:
            raise ValueError(f"kind is one of {', '.join(ZOOM_KINDS)}")
        if not is_number(self.margin) or not 0.0 <= self.margin <= MAX_ZOOM_MARGIN:
            raise ValueError(f"margin is between 0 and {MAX_ZOOM_MARGIN}")
        if self.kind == "extent":
            if self.extent is None:
                raise ValueError("zooming to an extent needs the extent")
            if self.layer_id is not None:
                raise ValueError("zooming to an extent names no layer")
        else:
            if not isinstance(self.layer_id, str) or not self.layer_id:
                raise ValueError(f"zooming to a {self.kind} needs a layer id")
            if self.extent is not None:
                raise ValueError(f"zooming to a {self.kind} carries no extent")

    @classmethod
    def layer(cls, layer_id: str, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to one layer's extent.

        Args:
            layer_id: The layer to frame.
            margin: How much of the target's span to leave around it.

        Returns:
            The target ``zoom_to`` takes.
        """
        return cls(kind="layer", layer_id=layer_id, margin=margin)

    @classmethod
    def selection(cls, layer_id: str, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to the features selected in one layer.

        Args:
            layer_id: The layer whose selection is framed.
            margin: How much of the target's span to leave around it.

        Returns:
            The target ``zoom_to`` takes.
        """
        return cls(kind="selection", layer_id=layer_id, margin=margin)

    @classmethod
    def to_extent(cls, extent: CanvasExtent, *, margin: float = 0.0) -> ZoomTarget:
        """Zoom to a box the caller computed.

        Args:
            extent: The box to frame.
            margin: How much of the target's span to leave around it.

        Returns:
            The target ``zoom_to`` takes.
        """
        return cls(kind="extent", extent=extent, margin=margin)

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "layer_id": self.layer_id,
            "extent": None if self.extent is None else self.extent.to_wire(),
            "margin": self.margin,
        }

    @classmethod
    def from_wire(cls, value: Any) -> ZoomTarget:
        """Read one target, refusing a field it does not know.

        Args:
            value: The mapping a page sent.
        """
        if not isinstance(value, Mapping):
            raise TypeError("a ZoomTarget is a mapping")
        unknown = set(value) - {"kind", "layer_id", "extent", "margin"}
        if unknown:
            raise ValueError(f"a ZoomTarget has no field {min(unknown)!r}")
        if "kind" not in value:
            raise ValueError("a ZoomTarget needs a kind")
        raw_extent = value.get("extent")
        return cls(
            kind=value["kind"],
            layer_id=value.get("layer_id"),
            extent=None if raw_extent is None else CanvasExtent.from_wire(raw_extent),
            margin=value.get("margin", 0.0),
        )
