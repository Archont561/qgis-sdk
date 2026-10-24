"""Layer reads the reference workflow needs; not a ``QgsVectorLayer`` mirror."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from qgis_sdk.models import VectorLayerInfo


class Layers(Protocol):
    """Open local vector datasets and read layer state.

    No method edits geometry or attributes: in-place editing, transactions and
    undo are out of scope for this slice (decision-19). Implementations raise
    ``QgisSdkLayerNotFoundError`` for an unknown layer identifier or dataset.
    """

    def open_vector(self, source: Path) -> VectorLayerInfo:
        """Open a local vector dataset and return its description."""
        ...

    def list_layers(self) -> tuple[VectorLayerInfo, ...]:
        """Return every layer this runtime has opened, in the order opened."""
        ...

    def layer(self, layer_id: str) -> VectorLayerInfo:
        """Return the description of one opened layer."""
        ...

    def selection(self, layer_id: str) -> tuple[int, ...]:
        """Return selected feature ids; an empty tuple means nothing selected."""
        ...
