"""Project membership, requested only after an operation has succeeded."""

from __future__ import annotations

from typing import Protocol


class Project(Protocol):
    """Add owned layers to the open project and read its current membership.

    ``add_layer`` is deliberately separate from producing a layer: decision-19
    adds an output to the project only after successful completion, so the caller
    decides when that moment is and this contract never mutates on its own.
    Adding a layer the runtime does not own raises ``QgisSdkLayerNotFoundError``;
    adding the same layer twice leaves one entry.
    """

    def layer_ids(self) -> tuple[str, ...]:
        """Return the project's layer ids in project order."""
        ...

    def add_layer(self, layer_id: str) -> None:
        """Add an owned layer to the project."""
        ...
