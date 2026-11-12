"""Source capture: identify only qualified direct local datasets."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProviderRegistry, QgsVectorLayer

import qgis_sdk.exports as export_policy

__all__ = ["capture_source"]

# These OGR drivers have a directly identifiable local dataset. Indirect
# providers (notably VRT) can refer to other files and must fail closed.
_LOCAL_SOURCE_DRIVERS = frozenset({"GeoJSON", "GPKG", "ESRI Shapefile"})


def _is_local_path(path: object) -> bool:
    """Whether a decoded source names a path on this machine.

    A provider may answer no path at all, a relative one, or a URI -
    ``/vsizip//…`` and ``postgres://…`` alike - and none of those is a file this
    process may describe.
    """
    if not isinstance(path, str) or not path:
        return False
    return "://" not in path


def capture_source(layer: QgsVectorLayer) -> export_policy.SourceIdentity | None:
    """Identify only qualified direct local datasets; leave others unexportable."""
    try:
        provider = layer.dataProvider()
        if (
            layer.providerType() != "ogr"
            or provider.storageType() not in _LOCAL_SOURCE_DRIVERS
        ):
            return None
        decoded = QgsProviderRegistry.instance().decodeUri(
            layer.providerType(), layer.source()
        )
        path = decoded.get("path")
        if not _is_local_path(path) or decoded.get("vsiPrefix"):
            return None
        return export_policy.capture_source(Path(path))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        # A source that cannot be decoded remains readable, but cannot be
        # exported because its physical dataset cannot be protected safely.
        return None
