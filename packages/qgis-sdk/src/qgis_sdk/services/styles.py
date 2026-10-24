"""Apply reviewed packaged layer styles; UI theming is a separate capability."""

from __future__ import annotations

from typing import Protocol


class Styles(Protocol):
    """Apply a packaged style resource to a compatible layer.

    The style is named by its catalog identifier (see
    :mod:`qgis_sdk.resources`), resolved by the adapter from the installed package
    rather than an ambient path. An unknown layer raises
    ``QgisSdkLayerNotFoundError``, an unknown identifier raises
    ``QgisSdkStyleNotFoundError``, and a target the style cannot express raises
    ``QgisSdkStyleIncompatibleError`` naming every mismatch at once - a refused
    application never leaves a partial style behind. Applying a style never
    mutates the application stylesheet or palette (decision-16).
    """

    def apply_style(self, layer_id: str, style: str) -> None:
        """Apply one packaged style resource to an owned layer."""
        ...
