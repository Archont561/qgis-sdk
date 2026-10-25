"""QGIS-free description of a packaged, reviewed layer style.

The catalog that names styles lives in :mod:`qgis_sdk.resources`; this module
holds the value type and the one compatibility rule every backend shares, so a
fake and the PyQGIS adapter cannot disagree about what "compatible" means.
"""

from __future__ import annotations

from dataclasses import dataclass

from .layers import GeometryType, VectorLayerInfo

__all__ = ["StyleSpec"]


@dataclass(frozen=True, slots=True)
class StyleSpec:
    """One reviewed style resource and the layers it may be applied to."""

    id: str
    resource: str
    geometry_type: GeometryType
    required_fields: tuple[str, ...] = ()

    def incompatibilities(self, layer: VectorLayerInfo) -> tuple[str, ...]:
        """Return every reason this style cannot be applied, empty when it can.

        All reasons are reported, not the first one: a caller fixing a style
        mismatch should not need one round trip per problem. The message never
        includes the layer object, only its description.
        """
        reasons: list[str] = []
        if layer.geometry_type != self.geometry_type:
            reasons.append(
                f"style targets {self.geometry_type} geometry; "
                f"the layer is {layer.geometry_type}"
            )
        missing = [
            field for field in self.required_fields if field not in layer.field_names
        ]
        if missing:
            listed = ", ".join(missing)
            reasons.append(f"the layer is missing required field(s): {listed}")
        return tuple(reasons)
