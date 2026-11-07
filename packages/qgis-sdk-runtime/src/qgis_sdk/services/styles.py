"""Layer appearance: packaged styles, symbology, labelling and the style manager.

decision-16 split layer styles from UI themes and told this service not to mirror
the renderer API; decision-54 point 4 then asked for the rest of the curated
surface - renderers, symbols, labelling and the style manager, with QML and SLD
both ways. Both live here because they are one capability: *how a layer is
drawn*, whether the instruction comes from a reviewed package, a description or
a document.

The service acts on **owned vector layers only**. A mesh, a point cloud, a
vector tile layer, an annotation layer or a raster is refused with
``QgisSdkUnsupportedCapabilityError`` naming its kind: QGIS's vector renderer
machinery does not apply to them, and a service that answered a single-symbol
renderer for a mesh would describe something no map draws.
"""

from __future__ import annotations

from typing import Protocol

from qgis_sdk.models.symbology import (
    Labelling,
    Renderer,
    StyleEntry,
    StyleText,
)


class Styles(Protocol):
    """Read and set how a layer is drawn.

    The style half (TASK-25.4) applies a *packaged* style named by its catalog
    identifier; an unknown layer raises ``QgisSdkLayerNotFoundError`` and a target
    the style cannot express raises ``QgisSdkStyleIncompatibleError`` naming every
    mismatch at once - a refused application never leaves a partial style behind.
    Applying a style never mutates the application stylesheet or palette
    (decision-16).

    The symbology half (TASK-93) reads and writes a :class:`Renderer` description
    and a :class:`Labelling` description, and moves a layer's style in and out as
    QML or SLD **text**. What comes back from a get is what a previous set wrote,
    so a round trip is one assertion on both backends.
    """

    def apply_style(self, layer_id: str, style: str) -> None:
        """Apply one packaged style resource to an owned layer."""
        ...

    def symbology(self, layer_id: str) -> Renderer:
        """Return the description of the renderer drawing ``layer_id``."""
        ...

    def set_symbology(self, layer_id: str, renderer: Renderer) -> None:
        """Draw ``layer_id`` with ``renderer``, replacing the current renderer."""
        ...

    def labelling(self, layer_id: str) -> Labelling:
        """Return how ``layer_id``'s features are labelled."""
        ...

    def set_labelling(self, layer_id: str, labelling: Labelling) -> None:
        """Label ``layer_id``'s features as ``labelling`` says, or switch it off."""
        ...

    def list_styles(self, kind: str | None = None) -> tuple[StyleEntry, ...]:
        """Return what the style manager offers, optionally of one kind.

        ``kind`` is one of ``symbol``, ``color_ramp`` and ``label_settings``; an
        unknown kind raises ``ValueError`` rather than answering an empty list,
        because "the manager holds nothing of that kind" and "you spelled the
        kind wrong" are different answers.
        """
        ...

    def export_style(self, layer_id: str, format: str) -> StyleText:
        """Return ``layer_id``'s style as QML or SLD text."""
        ...

    def import_style(self, layer_id: str, text: str, format: str) -> None:
        """Apply QML or SLD text to ``layer_id``, replacing its current style."""
        ...
